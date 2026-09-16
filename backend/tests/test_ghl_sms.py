"""GHL Conversations SMS — mocked HTTP only. No live GHL or Twilio network."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "subsidekick_ghl_sms_test")
os.environ["SKIP_BACKGROUND_JOBS"] = "1"
for _k in (
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM",
    "TWILIO_FROM_NUMBER",
    "GHL_ACCESS_TOKEN",
    "GHL_LOCATION_ID",
    "GHL_PUBLIC_KEY",
    "TWILIO_SKIP_SIGNATURE_CHECK",
    "ALLOW_DEV_LOGIN",
):
    os.environ.pop(_k, None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ghl_sms as gs


TOKEN = "ghl_test_token_not_real"
LOC = "loc_cornbred_test"
FROM = "+12295857126"
TO = "+19045550101"
MSG = "SubSidekick weekly recap — drafts only, not sent."


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_sms_provider_prefers_twilio_then_ghl(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GHL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GHL_LOCATION_ID", raising=False)
    assert gs.sms_provider() is None
    monkeypatch.setenv("GHL_ACCESS_TOKEN", TOKEN)
    assert gs.ghl_configured() is True
    assert gs.sms_provider() is None  # location required for SMS
    monkeypatch.setenv("GHL_LOCATION_ID", LOC)
    assert gs.sms_provider() == "ghl"
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxxxxxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "twilio_token")
    assert gs.sms_provider() == "twilio"
    assert gs.twilio_configured() is True


def test_sms_from_number_aliases_and_default(monkeypatch):
    monkeypatch.delenv("TWILIO_FROM", raising=False)
    monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
    monkeypatch.delenv("twilio_from_number", raising=False)
    assert gs.sms_from_number() == "+12295857126"
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15550001111")
    assert gs.sms_from_number() == "+15550001111"
    monkeypatch.setenv("TWILIO_FROM", "+15550002222")
    assert gs.sms_from_number() == "+15550002222"


def test_send_lookup_then_message(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return FakeResp(200, {"contacts": [{"id": "ct_existing", "phone": TO}]})

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        return FakeResp(200, {"messageId": "msg_1", "conversationId": "cv_1"})

    result = gs.send_sms(
        TO, MSG,
        access_token=TOKEN, location_id=LOC, from_number=FROM,
        http_get=fake_get, http_post=fake_post,
    )
    assert result["provider"] == "ghl"
    assert result["sid"] == "msg_1"
    assert result["contact_id"] == "ct_existing"
    assert result["contact_source"] == "lookup"
    assert [c[0] for c in calls] == ["GET", "POST"]
    get_url, get_kw = calls[0][1], calls[0][2]
    assert get_url == "https://services.leadconnectorhq.com/contacts/"
    assert get_kw["params"]["locationId"] == LOC
    assert get_kw["params"]["query"] == TO
    assert get_kw["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert get_kw["headers"]["Version"] == "2021-07-28"
    post_url, post_kw = calls[1][1], calls[1][2]
    assert post_url == "https://services.leadconnectorhq.com/conversations/messages"
    body = post_kw["json"]
    assert body["type"] == "SMS"
    assert body["contactId"] == "ct_existing"
    assert body["message"] == MSG
    assert body["fromNumber"] == FROM
    assert body["toNumber"] == TO
    assert "upsert" not in post_url


def test_send_upserts_when_lookup_empty():
    calls = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return FakeResp(200, {"contacts": []})

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        if url.endswith("/contacts/upsert"):
            return FakeResp(200, {"new": True, "contact": {"id": "ct_new", "phone": TO}})
        assert url.endswith("/conversations/messages")
        return FakeResp(201, {"message": {"id": "msg_new", "conversationId": "cv_new"}})

    result = gs.send_sms(
        TO, MSG,
        access_token=TOKEN, location_id=LOC, from_number=FROM,
        http_get=fake_get, http_post=fake_post,
    )
    assert result["provider"] == "ghl"
    assert result["sid"] == "msg_new"
    assert result["contact_id"] == "ct_new"
    assert result["contact_source"] == "upsert"
    methods_urls = [(c[0], c[1]) for c in calls]
    assert methods_urls[0][0] == "GET"
    assert methods_urls[1] == ("POST", "https://services.leadconnectorhq.com/contacts/upsert")
    assert methods_urls[2][1].endswith("/conversations/messages")
    upsert_json = calls[1][2]["json"]
    assert upsert_json["locationId"] == LOC
    assert upsert_json["phone"] == TO
    send_json = calls[2][2]["json"]
    assert send_json["contactId"] == "ct_new"
    assert send_json["fromNumber"] == FROM


def test_send_uses_default_from_number():
    def fake_get(url, **kwargs):
        return FakeResp(200, {"contacts": [{"id": "ct1", "phone": TO}]})

    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return FakeResp(200, {"messageId": "m"})

    gs.send_sms(TO, MSG, access_token=TOKEN, location_id=LOC, http_get=fake_get, http_post=fake_post)
    assert captured["json"]["fromNumber"] == "+12295857126"


def test_lookup_http_error_does_not_send_message():
    def fake_get(url, **kwargs):
        return FakeResp(401, {"message": "Unauthorized"})

    def fake_post(url, **kwargs):
        raise AssertionError("must not POST after failed lookup")

    try:
        gs.send_sms(TO, MSG, access_token=TOKEN, location_id=LOC, http_get=fake_get, http_post=fake_post)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "401" in str(e)
        assert TOKEN not in str(e)


def test_parse_inbound_sms_and_skip_non_sms():
    sms = gs.parse_inbound_payload({
        "type": "InboundMessage",
        "locationId": LOC,
        "body": "GC added extra work change order",
        "contactId": "ct1",
        "messageId": "mid1",
        "direction": "inbound",
        "messageType": "SMS",
        "from": TO,
        "to": FROM,
    })
    assert sms is not None
    assert sms["body"].startswith("GC added")
    assert sms["from_number"] == TO
    assert sms["message_id"] == "mid1"

    assert gs.parse_inbound_payload({
        "type": "InboundMessage", "messageType": "CALL", "from": TO, "body": "voicemail",
        "direction": "inbound",
    }) is None
    assert gs.parse_inbound_payload({
        "type": "OutboundMessage", "messageType": "SMS", "from": FROM, "to": TO,
        "body": "we texted you", "direction": "outbound",
    }) is None
    assert gs.parse_inbound_payload({"type": "InboundMessage", "from": TO, "body": ""}) is None
