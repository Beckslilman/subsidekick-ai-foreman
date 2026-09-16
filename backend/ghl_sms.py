"""GoHighLevel / LeadConnector Conversations SMS (no Twilio SID required).

Credentials are read from process env only — never persist tokens.
Outbound SMS: POST /conversations/messages (Version 2021-07-28) after finding
or upserting a location contact by phone.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

import requests

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"
DEFAULT_FROM_NUMBER = "+12295857126"
HTTP_TIMEOUT = 20

GetFn = Callable[..., Any]
PostFn = Callable[..., Any]


def env_value(*names: str, default: str = "") -> str:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return default


def sms_from_number() -> str:
    """LC/Twilio from number: TWILIO_FROM, TWILIO_FROM_NUMBER, or Trey's Sidekick number."""
    return env_value("TWILIO_FROM", "TWILIO_FROM_NUMBER", "twilio_from_number", default=DEFAULT_FROM_NUMBER)


def ghl_access_token() -> str:
    return env_value("GHL_ACCESS_TOKEN")


def ghl_location_id() -> str:
    return env_value("GHL_LOCATION_ID")


def twilio_account_sid() -> str:
    return env_value("TWILIO_ACCOUNT_SID")


def twilio_auth_token() -> str:
    return env_value("TWILIO_AUTH_TOKEN")


def twilio_configured() -> bool:
    return bool(twilio_account_sid() and twilio_auth_token())


def ghl_configured() -> bool:
    """Voice AI / PIT presence — matches existing status field (token is enough)."""
    return bool(ghl_access_token())


def ghl_sms_ready() -> bool:
    return bool(ghl_access_token() and ghl_location_id())


def sms_provider() -> Optional[str]:
    """Prefer Twilio when SID+token are present; otherwise GHL Conversations."""
    if twilio_configured():
        return "twilio"
    if ghl_sms_ready():
        return "ghl"
    return None


def normalize_e164(phone: str) -> str:
    raw = (phone or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        raise ValueError("invalid phone number")
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def phone_digits(phone: Optional[str]) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def phones_match(a: Optional[str], b: Optional[str]) -> bool:
    da, db = phone_digits(a), phone_digits(b)
    if not da or not db:
        return False
    if da == db:
        return True
    if len(da) >= 10 and len(db) >= 10:
        return da[-10:] == db[-10:]
    return False


def ghl_headers(access_token: Optional[str] = None) -> dict[str, str]:
    token = (access_token if access_token is not None else ghl_access_token()).strip()
    return {
        "Authorization": f"Bearer {token}",
        "Version": GHL_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _json_or_empty(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {}


def _error_snippet(resp: requests.Response) -> str:
    text = (resp.text or "")[:300]
    return text.replace("\n", " ")


def _check(resp: requests.Response, action: str) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"GHL {action} failed HTTP {resp.status_code}: {_error_snippet(resp)}")


def _contact_id_from_payload(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else payload
    cid = contact.get("id") or contact.get("contactId") or payload.get("contactId") or payload.get("id")
    if cid:
        return str(cid)
    return None


def lookup_contact_id(
    phone: str,
    *,
    access_token: Optional[str] = None,
    location_id: Optional[str] = None,
    http_get: Optional[GetFn] = None,
) -> Optional[str]:
    token = (access_token if access_token is not None else ghl_access_token()).strip()
    loc = (location_id if location_id is not None else ghl_location_id()).strip()
    e164 = normalize_e164(phone)
    getter = http_get or requests.get
    url = f"{GHL_API_BASE}/contacts/"
    resp = getter(
        url,
        headers=ghl_headers(token),
        params={"locationId": loc, "query": e164},
        timeout=HTTP_TIMEOUT,
    )
    _check(resp, "contact lookup")
    data = _json_or_empty(resp)
    contacts = data.get("contacts") if isinstance(data, dict) else None
    if not isinstance(contacts, list):
        contacts = data if isinstance(data, list) else []
    for c in contacts:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or c.get("contactId")
        if cid and phones_match(c.get("phone") or c.get("phoneNumber") or e164, e164):
            return str(cid)
        if cid and not (c.get("phone") or c.get("phoneNumber")):
            return str(cid)
    if contacts and isinstance(contacts[0], dict):
        cid = contacts[0].get("id") or contacts[0].get("contactId")
        if cid:
            return str(cid)
    return None


def upsert_contact_id(
    phone: str,
    *,
    access_token: Optional[str] = None,
    location_id: Optional[str] = None,
    http_post: Optional[PostFn] = None,
) -> str:
    token = (access_token if access_token is not None else ghl_access_token()).strip()
    loc = (location_id if location_id is not None else ghl_location_id()).strip()
    e164 = normalize_e164(phone)
    poster = http_post or requests.post
    url = f"{GHL_API_BASE}/contacts/upsert"
    resp = poster(
        url,
        headers=ghl_headers(token),
        json={"locationId": loc, "phone": e164, "source": "SubSidekick"},
        timeout=HTTP_TIMEOUT,
    )
    _check(resp, "contact upsert")
    cid = _contact_id_from_payload(_json_or_empty(resp))
    if not cid:
        raise RuntimeError("GHL contact upsert returned no contact id")
    return cid


def find_or_upsert_contact_id(
    phone: str,
    *,
    access_token: Optional[str] = None,
    location_id: Optional[str] = None,
    http_get: Optional[GetFn] = None,
    http_post: Optional[PostFn] = None,
) -> tuple[str, str]:
    """Return (contact_id, 'lookup'|'upsert')."""
    found = lookup_contact_id(
        phone, access_token=access_token, location_id=location_id, http_get=http_get
    )
    if found:
        return found, "lookup"
    created = upsert_contact_id(
        phone, access_token=access_token, location_id=location_id, http_post=http_post
    )
    return created, "upsert"


def post_conversation_sms(
    *,
    contact_id: str,
    message: str,
    to: str,
    from_number: Optional[str] = None,
    access_token: Optional[str] = None,
    http_post: Optional[PostFn] = None,
) -> dict:
    token = (access_token if access_token is not None else ghl_access_token()).strip()
    poster = http_post or requests.post
    url = f"{GHL_API_BASE}/conversations/messages"
    payload = {
        "type": "SMS",
        "contactId": contact_id,
        "message": message,
        "fromNumber": from_number or sms_from_number(),
        "toNumber": normalize_e164(to),
    }
    resp = poster(url, headers=ghl_headers(token), json=payload, timeout=HTTP_TIMEOUT)
    _check(resp, "send SMS")
    data = _json_or_empty(resp)
    msg = data.get("message") if isinstance(data.get("message"), dict) else {}
    sid = (
        data.get("messageId")
        or msg.get("id")
        or msg.get("messageId")
        or data.get("id")
        or ""
    )
    return {
        "provider": "ghl",
        "sid": str(sid) if sid else None,
        "to": normalize_e164(to),
        "body": message,
        "contact_id": contact_id,
        "conversation_id": data.get("conversationId") or msg.get("conversationId"),
    }


def send_sms(
    to: str,
    message: str,
    *,
    access_token: Optional[str] = None,
    location_id: Optional[str] = None,
    from_number: Optional[str] = None,
    http_get: Optional[GetFn] = None,
    http_post: Optional[PostFn] = None,
) -> dict:
    token = (access_token if access_token is not None else ghl_access_token()).strip()
    loc = (location_id if location_id is not None else ghl_location_id()).strip()
    if not token or not loc:
        raise RuntimeError("GHL_ACCESS_TOKEN and GHL_LOCATION_ID are required to send SMS")
    contact_id, source = find_or_upsert_contact_id(
        to,
        access_token=token,
        location_id=loc,
        http_get=http_get,
        http_post=http_post,
    )
    result = post_conversation_sms(
        contact_id=contact_id,
        message=message,
        to=to,
        from_number=from_number or sms_from_number(),
        access_token=token,
        http_post=http_post,
    )
    result["contact_source"] = source
    return result


def parse_inbound_payload(payload: Any) -> Optional[dict]:
    """Normalize a GHL InboundMessage webhook body. Returns None if not inbound SMS."""
    if isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    event_type = str(data.get("type") or payload.get("type") or "").strip()
    direction = str(data.get("direction") or "inbound").strip().lower()
    if event_type.lower() in {"outboundmessage", "outbound"}:
        return None
    if direction in {"outbound", "out"}:
        return None
    mt = str(data.get("messageType") or data.get("messageTypeString") or "").strip().upper()
    if mt in {"CALL", "EMAIL", "WHATSAPP", "FB", "IG", "LIVE_CHAT", "TYPE_CALL", "TYPE_EMAIL", "TYPE_WHATSAPP"}:
        return None
    body = (data.get("body") or data.get("message") or data.get("text") or "").strip()
    from_number = (data.get("from") or data.get("fromNumber") or data.get("phone") or "").strip()
    to_number = (data.get("to") or data.get("toNumber") or "").strip()
    is_sms = mt in {"", "SMS", "TYPE_SMS", "2"} or event_type.lower() in {"inboundmessage", "inbound", ""}
    if not is_sms or not body or not from_number:
        return None
    message_id = str(data.get("messageId") or data.get("id") or "").strip()
    return {
        "from_number": from_number,
        "to_number": to_number,
        "body": body,
        "contact_id": str(data.get("contactId") or "") or None,
        "message_id": message_id or None,
        "conversation_id": str(data.get("conversationId") or "") or None,
        "location_id": str(data.get("locationId") or "") or None,
        "message_type": mt or "SMS",
    }
