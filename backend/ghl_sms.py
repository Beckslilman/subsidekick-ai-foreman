"""GoHighLevel Conversations SMS — used when Twilio SID/token are absent.

Credentials are read from process env only (Deployment Secrets). Never persist tokens.
Live GHL traffic is mocked in tests; this module does not reach the network in CI.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

import requests

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"
DEFAULT_FROM_NUMBER = "+12295857126"

HttpFn = Callable[..., Any]


class GhlHttpError(RuntimeError):
    pass


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def sms_from_number() -> str:
    """LC / Twilio from-number. TWILIO_FROM_NUMBER, TWILIO_FROM, or twilio_from_number; default Trey's LC number."""
    for key in ("TWILIO_FROM_NUMBER", "TWILIO_FROM", "twilio_from_number"):
        val = _env(key)
        if val:
            return val
    return DEFAULT_FROM_NUMBER


def ghl_access_token() -> str:
    return _env("GHL_ACCESS_TOKEN")


def ghl_location_id() -> str:
    return _env("GHL_LOCATION_ID")


def twilio_ready() -> bool:
    return bool(_env("TWILIO_ACCOUNT_SID") and _env("TWILIO_AUTH_TOKEN"))


def ghl_token_configured() -> bool:
    return bool(ghl_access_token())


def ghl_sms_ready() -> bool:
    return bool(ghl_access_token() and ghl_location_id() and sms_from_number())


def sms_provider() -> Optional[str]:
    """Preferred live SMS path: Twilio when SID+token exist, else GHL Conversations, else None (outbox)."""
    if twilio_ready():
        return "twilio"
    if ghl_sms_ready():
        return "ghl"
    return None


def sms_status() -> dict:
    provider = sms_provider()
    return {
        "sms_provider": provider,
        "twilio_configured": twilio_ready(),
        "ghl_configured": ghl_token_configured(),
        "sms_ready": provider is not None,
        "twilio_from": sms_from_number() or None,
    }


def normalize_e164(phone: Optional[str]) -> str:
    raw = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    if not raw:
        return ""
    if not raw.startswith("+"):
        if len(raw) == 10:
            raw = "+1" + raw
        elif len(raw) == 11 and raw.startswith("1"):
            raw = "+" + raw
        else:
            raw = "+" + raw
    return raw


def ghl_headers() -> dict:
    return {
        "Authorization": f"Bearer {ghl_access_token()}",
        "Version": GHL_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _default_http(method: str, url: str, **kwargs):
    return requests.request(method, url, **kwargs)


def _digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _contact_id_from_record(contact: dict) -> str:
    if not isinstance(contact, dict):
        return ""
    return str(contact.get("id") or contact.get("contactId") or contact.get("contact_id") or "")


def _match_contact_id(contacts: list, e164: str) -> str:
    want = _digits(e164)
    matched: list[str] = []
    for c in contacts:
        if not isinstance(c, dict):
            continue
        cid = _contact_id_from_record(c)
        phone = normalize_e164(str(c.get("phone") or c.get("phoneNumber") or ""))
        if cid and phone and _digits(phone) == want:
            return cid
        if cid:
            matched.append(cid)
    # Phone-query search sometimes omits the phone field; accept a single hit.
    if len(matched) == 1:
        return matched[0]
    return ""


def find_or_upsert_contact(phone: str, http: Optional[HttpFn] = None) -> str:
    """Find a location contact by phone, or upsert one. Returns GHL contactId."""
    http = http or _default_http
    loc = ghl_location_id()
    e164 = normalize_e164(phone)
    if not loc or not e164:
        raise GhlHttpError("GHL location or phone missing for contact upsert")
    headers = ghl_headers()

    search = http(
        "GET",
        f"{GHL_API_BASE}/contacts/",
        params={"locationId": loc, "query": e164, "limit": 5},
        headers=headers,
        timeout=30,
    )
    if getattr(search, "ok", False):
        try:
            payload = search.json() if search.content else {}
        except Exception:
            payload = {}
        contacts = []
        if isinstance(payload, dict):
            contacts = payload.get("contacts") or payload.get("data") or []
        cid = _match_contact_id(contacts if isinstance(contacts, list) else [], e164)
        if cid:
            return cid

    upsert = http(
        "POST",
        f"{GHL_API_BASE}/contacts/upsert",
        headers=headers,
        json={"locationId": loc, "phone": e164, "source": "public api"},
        timeout=30,
    )
    if not getattr(upsert, "ok", False):
        text = getattr(upsert, "text", "") or ""
        status = getattr(upsert, "status_code", "?")
        raise GhlHttpError(f"GHL contact upsert failed ({status}): {text[:300]}")
    try:
        data = upsert.json() if upsert.content else {}
    except Exception:
        data = {}
    contact = data.get("contact") if isinstance(data, dict) else None
    cid = _contact_id_from_record(contact if isinstance(contact, dict) else {}) or (
        str(data.get("id") or data.get("contactId") or "") if isinstance(data, dict) else ""
    )
    if not cid:
        raise GhlHttpError("GHL upsert did not return a contact id")
    return cid


def send_ghl_sms(to: str, body: str, http: Optional[HttpFn] = None) -> dict:
    """Send an SMS via HighLevel Conversations API. Never hits the network when `http` is injected."""
    to_e164 = normalize_e164(to)
    if not ghl_sms_ready():
        return {"provider": "outbox", "to": to_e164 or to, "body": body, "error": "ghl_not_configured"}
    http = http or _default_http
    try:
        contact_id = find_or_upsert_contact(to_e164, http=http)
        from_number = sms_from_number()
        resp = http(
            "POST",
            f"{GHL_API_BASE}/conversations/messages",
            headers=ghl_headers(),
            json={
                "type": "SMS",
                "contactId": contact_id,
                "message": body,
                "fromNumber": from_number,
                "toNumber": to_e164,
            },
            timeout=30,
        )
        if not getattr(resp, "ok", False):
            text = getattr(resp, "text", "") or ""
            status = getattr(resp, "status_code", "?")
            raise GhlHttpError(f"GHL send message failed ({status}): {text[:300]}")
        try:
            data = resp.json() if resp.content else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        sid = data.get("messageId") or data.get("message_id") or data.get("id")
        return {
            "provider": "ghl",
            "sid": sid,
            "contact_id": contact_id,
            "conversation_id": data.get("conversationId"),
            "to": to_e164,
            "body": body,
            "from": from_number,
        }
    except Exception as e:
        return {"provider": "outbox", "to": to_e164 or to, "body": body, "error": str(e)}


def _unwrap_inbound_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}
    for key in ("data", "customData", "payload", "message"):
        nested = payload.get(key)
        if isinstance(nested, dict) and (
            nested.get("from") or nested.get("fromNumber") or nested.get("body") or nested.get("phone")
        ):
            return nested
    return payload


def parse_ghl_inbound_sms(payload: Any) -> Optional[dict]:
    """Normalize a GHL InboundMessage (or workflow JSON) into from/to/body/message_id.

    Returns None when the event is not an inbound SMS (calls, email, outbound).
    """
    if not isinstance(payload, dict):
        return None
    data = _unwrap_inbound_payload(payload)
    event_type = str(payload.get("type") or data.get("type") or "")
    msg_type = str(data.get("messageType") or data.get("message_type") or data.get("messageTypeString") or "").upper()
    direction = str(data.get("direction") or "inbound").lower()

    if direction == "outbound" or event_type in {"OutboundMessage", "outboundMessage"}:
        return None
    if msg_type in {"CALL", "TYPE_CALL", "EMAIL", "WHATSAPP", "TYPE_EMAIL", "TYPE_WHATSAPP", "TYPE_VOICEMAIL"}:
        return None
    if msg_type and msg_type not in {"SMS", "TYPE_SMS"} and "SMS" not in msg_type:
        return None

    from_number = normalize_e164(
        str(
            data.get("from")
            or data.get("fromNumber")
            or data.get("phone")
            or (data.get("contact") or {}).get("phone")
            or ""
        )
    )
    to_number = normalize_e164(str(data.get("to") or data.get("toNumber") or ""))
    body = str(data.get("body") or data.get("message") or data.get("text") or "").strip()
    message_id = str(
        data.get("messageId") or data.get("message_id") or data.get("id") or payload.get("messageId") or ""
    ).strip()

    if not from_number or not body:
        return None
    loc = str(data.get("locationId") or payload.get("locationId") or "")
    configured_loc = ghl_location_id()
    if loc and configured_loc and loc != configured_loc:
        return None

    return {
        "from": from_number,
        "to": to_number,
        "body": body,
        "message_id": message_id,
        "contact_id": str(data.get("contactId") or ""),
        "location_id": loc,
    }
