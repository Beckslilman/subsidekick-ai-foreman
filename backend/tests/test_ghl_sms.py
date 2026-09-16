"""GHL Conversations SMS fallback — mocked HTTP only, no live GHL/Twilio."""
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
    "TWILIO_FROM_NUMBER",
    "TWILIO_FROM",
    "twilio_from_number",
    "GHL_ACCESS_TOKEN",
    "GHL_LOCATION_ID",
    "GHL_PUBLIC_KEY",
    "TWILIO_SKIP_SIGNATURE_CHECK",
    "ALLOW_DEV_LOGIN",
    "ENVIRONMENT",
    "APP_ENV",
    "ENV",
    "NODE_ENV",
):
    os.environ.pop(_k, None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import base64

import ghl_sms
import server
from webhook_security import ghl_signature_ok


class FakeResponse:
    def __init__(self, status=200, json_data=None, text=""):
        self.status_code = status
        self._json = json_data if json_data is not None else {}
        self.text = text or json.dumps(self._json)
        self.content = self.text.encode() if self.text else b""
        self.ok = 200 <= status < 300

    def json(self):
        return self._json


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.routes = []

    def add(self, method, url_part, response):
        self.routes.append((method.upper(), url_part, response))

    def __call__(self, method, url, **kwargs):
        rec = {"method": method.upper(), "url": url, **kwargs}
        self.calls.append(rec)
        for m, part, resp in self.routes:
            if m == rec["method"] and part in url:
                return resp(rec) if callable(resp) else resp
        raise AssertionError(f"unhandled {method} {url}")


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, n):
        return [dict(d) for d in self._docs[:n]]


class FakeCollection:
    def __init__(self, unique_keys=()):
        self.docs = []
        self.unique_keys = unique_keys

    def _match(self, doc, query):
        if not query:
            return True
        for k, v in query.items():
            if doc.get(k) != v:
                return False
        return True

    async def find_one(self, query, projection=None, sort=None):
        for d in self.docs:
            if self._match(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc):
        for key in self.unique_keys:
            if key in doc and any(d.get(key) == doc.get(key) for d in self.docs):
                raise DuplicateKeyError(f"dup {key}")
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id") or doc.get("message_id")})()

    async def create_index(self, *args, **kwargs):
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        return FakeCursor([d for d in self.docs if self._match(d, query)])


class FakeDB:
    def __init__(self):
        self.users = FakeCollection(unique_keys=("email", "user_id"))
        self.user_sessions = FakeCollection(unique_keys=("session_token",))
        self.team_members = FakeCollection()
        self.call_logs = FakeCollection()
        self.twilio_inbound_sids = FakeCollection(unique_keys=("message_sid",))
        self.ghl_events = FakeCollection(unique_keys=("event_id",))
        self.ghl_inbound_sids = FakeCollection(unique_keys=("message_id",))
        self.jobs = FakeCollection()
        self.change_orders = FakeCollection()
        self.back_charges = FakeCollection()
        self.schedule_changes = FakeCollection()
        self.chat_messages = FakeCollection()
        self.sms_outbox = FakeCollection()

    def __getattr__(self, name):
        coll = FakeCollection()
        setattr(self, name, coll)
        return coll


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def fail(*_a, **_k):
        raise RuntimeError("live GHL/Twilio HTTP is forbidden in these tests")

    monkeypatch.setattr(ghl_sms.requests, "request", fail)
    monkeypatch.setattr(ghl_sms.requests, "get", fail)
    monkeypatch.setattr(ghl_sms.requests, "post", fail)
    monkeypatch.setattr(ghl_sms.requests, "put", fail)
    for key in (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_FROM_NUMBER",
        "TWILIO_FROM",
        "twilio_from_number",
        "GHL_ACCESS_TOKEN",
        "GHL_LOCATION_ID",
        "GHL_PUBLIC_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def ghl_env(monkeypatch):
    monkeypatch.setenv("GHL_ACCESS_TOKEN", "pit_test_token")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc_cornbred")
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
    monkeypatch.delenv("TWILIO_FROM", raising=False)
    yield


def test_sms_provider_prefers_twilio(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("GHL_ACCESS_TOKEN", "pit")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc")
    assert ghl_sms.sms_provider() == "twilio"
    assert ghl_sms.twilio_ready() is True
    assert ghl_sms.ghl_sms_ready() is True


def test_sms_provider_ghl_when_twilio_blank(ghl_env):
    assert ghl_sms.sms_provider() == "ghl"
    st = ghl_sms.sms_status()
    assert st["sms_provider"] == "ghl"
    assert st["twilio_configured"] is False
    assert st["ghl_configured"] is True
    assert st["sms_ready"] is True
    assert st["twilio_from"] == "+12295857126"


def test_sms_provider_null_when_neither(monkeypatch):
    monkeypatch.delenv("GHL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GHL_LOCATION_ID", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    assert ghl_sms.sms_provider() is None
    assert ghl_sms.sms_status()["sms_ready"] is False


def test_from_number_env_aliases(monkeypatch):
    monkeypatch.setenv("TWILIO_FROM", "+15550001111")
    assert ghl_sms.sms_from_number() == "+15550001111"
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+12295857126")
    assert ghl_sms.sms_from_number() == "+12295857126"


def test_send_ghl_sms_lookup_then_message(ghl_env):
    http = FakeHttp()
    http.add("GET", "/contacts/", FakeResponse(200, {
        "contacts": [{"id": "ct_existing", "phone": "+19045550101"}],
    }))
    http.add("POST", "/conversations/messages", FakeResponse(201, {
        "conversationId": "conv_1", "messageId": "msg_99",
    }))
    result = ghl_sms.send_ghl_sms("+19045550101", "Morning briefing", http=http)
    assert result["provider"] == "ghl"
    assert result["sid"] == "msg_99"
    assert result["contact_id"] == "ct_existing"
    assert len(http.calls) == 2
    send = http.calls[1]
    assert send["headers"]["Authorization"] == "Bearer pit_test_token"
    assert send["headers"]["Version"] == "2021-07-28"
    assert send["json"] == {
        "type": "SMS",
        "contactId": "ct_existing",
        "message": "Morning briefing",
        "fromNumber": "+12295857126",
        "toNumber": "+19045550101",
    }
    assert not any("/contacts/upsert" in c["url"] for c in http.calls)


def test_send_ghl_sms_upserts_when_search_empty(ghl_env):
    http = FakeHttp()
    http.add("GET", "/contacts/", FakeResponse(200, {"contacts": []}))
    http.add("POST", "/contacts/upsert", FakeResponse(200, {
        "new": True, "contact": {"id": "ct_new", "phone": "+15551234567"},
    }))
    http.add("POST", "/conversations/messages", FakeResponse(201, {"messageId": "msg_new"}))
    result = ghl_sms.send_ghl_sms("5551234567", "Recovery text", http=http)
    assert result["provider"] == "ghl"
    assert result["sid"] == "msg_new"
    assert result["contact_id"] == "ct_new"
    upsert = next(c for c in http.calls if "/contacts/upsert" in c["url"])
    assert upsert["json"]["locationId"] == "loc_cornbred"
    assert upsert["json"]["phone"] == "+15551234567"


def test_send_ghl_sms_outbox_when_not_configured(monkeypatch):
    monkeypatch.delenv("GHL_ACCESS_TOKEN", raising=False)
    http = FakeHttp()
    result = ghl_sms.send_ghl_sms("+1555", "x", http=http)
    assert result["provider"] == "outbox"
    assert http.calls == []


def test_send_ghl_sms_outbox_on_http_error(ghl_env):
    http = FakeHttp()
    http.add("GET", "/contacts/", FakeResponse(200, {"contacts": []}))
    http.add("POST", "/contacts/upsert", FakeResponse(401, {"message": "Invalid token"}, text="Invalid token"))
    result = ghl_sms.send_ghl_sms("+19045550101", "hi", http=http)
    assert result["provider"] == "outbox"
    assert "401" in (result.get("error") or "")


def test_parse_inbound_sms_standard_payload():
    parsed = ghl_sms.parse_ghl_inbound_sms({
        "type": "InboundMessage",
        "locationId": "loc_cornbred",
        "body": "GC added extra work change order",
        "messageType": "SMS",
        "direction": "inbound",
        "from": "+19045550101",
        "to": "+12295857126",
        "messageId": "m1",
    })
    assert parsed["from"] == "+19045550101"
    assert parsed["body"].startswith("GC added")
    assert parsed["message_id"] == "m1"


def test_parse_inbound_skips_calls_and_outbound():
    assert ghl_sms.parse_ghl_inbound_sms({
        "type": "InboundMessage", "messageType": "CALL",
        "from": "+19045550101", "body": "voicemail",
    }) is None
    assert ghl_sms.parse_ghl_inbound_sms({
        "type": "OutboundMessage", "messageType": "SMS",
        "from": "+12295857126", "body": "we sent this", "direction": "outbound",
    }) is None


def test_parse_inbound_workflow_wrapper(monkeypatch):
    monkeypatch.setenv("GHL_LOCATION_ID", "loc_cornbred")
    parsed = ghl_sms.parse_ghl_inbound_sms({
        "data": {
            "from": "9045550101",
            "message": "Need a back charge on Oakwood",
            "to": "+12295857126",
            "locationId": "loc_cornbred",
            "messageType": "SMS",
        }
    })
    assert parsed["from"] == "+19045550101"
    assert "back charge" in parsed["body"]


# ---------- server routing ----------

class _FakeTwilioMsg:
    sid = "SM_test_sid"


class _FakeTwilioClient:
    def __init__(self):
        self.created = None

        class _Messages:
            def __init__(self, outer):
                self.outer = outer

            def create(self, **kwargs):
                self.outer.created = kwargs
                return _FakeTwilioMsg()

        self.messages = _Messages(self)


def test_send_sms_sync_uses_twilio_when_sid_token_present(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("GHL_ACCESS_TOKEN", "pit")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc")
    fake = _FakeTwilioClient()
    monkeypatch.setattr(server, "_twilio_client", lambda: fake)

    def boom(*_a, **_k):
        raise AssertionError("GHL must not be used when Twilio succeeds")

    monkeypatch.setattr(server, "send_ghl_sms", boom)
    result = server._send_sms_sync("+19045550101", "hello")
    assert result["provider"] == "twilio"
    assert result["sid"] == "SM_test_sid"
    assert fake.created["from_"] == "+12295857126"
    assert fake.created["to"] == "+19045550101"


def test_send_sms_sync_uses_ghl_when_twilio_blank(monkeypatch, ghl_env):
    monkeypatch.setattr(server, "_twilio_client", lambda: None)

    def fake_ghl(to, body, http=None):
        return {"provider": "ghl", "sid": "msg_ghl", "to": to, "body": body}

    monkeypatch.setattr(server, "send_ghl_sms", fake_ghl)
    result = server._send_sms_sync("+19045550101", "briefing")
    assert result["provider"] == "ghl"
    assert result["sid"] == "msg_ghl"


def test_send_sms_sync_outbox_when_neither(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GHL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GHL_LOCATION_ID", raising=False)
    result = server._send_sms_sync("+19045550101", "x")
    assert result["provider"] == "outbox"


def test_status_endpoint_reports_ghl_sms(monkeypatch, ghl_env):
    monkeypatch.setattr(server, "db", FakeDB())
    with TestClient(server.app, raise_server_exceptions=True) as client:
        r = client.get("/api/")
    assert r.status_code == 200
    body = r.json()
    assert body["sms_provider"] == "ghl"
    assert body["twilio_configured"] is False
    assert body["ghl_configured"] is True
    assert body["sms_ready"] is True
    assert body["twilio_from"] == "+12295857126"


def test_status_endpoint_reports_twilio_over_ghl(monkeypatch, ghl_env):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(server, "db", FakeDB())
    with TestClient(server.app, raise_server_exceptions=True) as client:
        r = client.get("/api/")
    assert r.json()["sms_provider"] == "twilio"
    assert r.json()["twilio_configured"] is True


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(server, "db", db)
    return db


@pytest.fixture
def api(fake_db):
    with TestClient(server.app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def known_super(fake_db):
    fake_db.team_members.docs.append({
        "id": "tm_rick",
        "user_id": "user_office",
        "name": "Rick Martinez",
        "phone_number": "+19045550101",
        "active": True,
    })
    fake_db.jobs.docs.append({
        "id": "job_riv",
        "user_id": "user_office",
        "name": "Riverstone Apartments",
        "gc": "Ellis",
        "crew": "Martinez Crew",
        "status": "active",
    })
    return fake_db.team_members.docs[0]


async def _fake_chat(user_id, content, channel="chat", from_number=None):
    return {
        "user_message": {"content": content},
        "ai_message": {"content": "Logged as a DRAFT for the office."},
        "action_hint": "change_order_draft_created",
        "route_hint": None,
        "extracted_drafts": ["co_from_ghl_sms"],
    }


def test_ghl_inbound_sms_known_number(api, known_super, monkeypatch, fake_db):
    monkeypatch.setattr(server, "_chat_with_context", _fake_chat)
    sent = []

    def fake_send(to, body, http=None):
        sent.append((to, body))
        return {"provider": "ghl", "sid": "reply_1"}

    monkeypatch.setattr(server, "send_ghl_sms", fake_send)
    monkeypatch.setenv("GHL_ACCESS_TOKEN", "pit")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc_cornbred")
    r = api.post("/api/webhooks/ghl/inbound-sms", json={
        "type": "InboundMessage",
        "locationId": "loc_cornbred",
        "body": "GC added extra work change order",
        "messageType": "SMS",
        "direction": "inbound",
        "from": "+19045550101",
        "to": "+12295857126",
        "messageId": "in_1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["drafts_created"] == ["co_from_ghl_sms"]
    assert body["reply_via"] == "ghl"
    assert fake_db.call_logs.docs[0]["channel"] == "sms"
    assert fake_db.call_logs.docs[0]["direction"] == "inbound"
    assert fake_db.call_logs.docs[0]["extracted_drafts"] == ["co_from_ghl_sms"]
    assert sent and sent[0][0] == "+19045550101"


def test_ghl_inbound_sms_dedupes_message_id(api, known_super, monkeypatch, fake_db):
    monkeypatch.setattr(server, "_chat_with_context", _fake_chat)
    payload = {
        "type": "InboundMessage",
        "messageType": "SMS",
        "from": "+19045550101",
        "to": "+12295857126",
        "body": "hello",
        "messageId": "dup_1",
        "direction": "inbound",
    }
    r1 = api.post("/api/webhooks/ghl/inbound-sms", json=payload)
    r2 = api.post("/api/webhooks/ghl/inbound-sms", json=payload)
    assert r1.status_code == 200 and r1.json()["ok"] is True
    assert r2.json().get("duplicate") is True
    assert len(fake_db.call_logs.docs) == 1


def test_ghl_inbound_sms_skips_call_events(api, known_super, fake_db):
    r = api.post("/api/webhooks/ghl/inbound-sms", json={
        "type": "InboundMessage",
        "messageType": "CALL",
        "from": "+19045550101",
        "body": "missed call",
    })
    assert r.status_code == 200
    assert r.json()["skipped"] == "not_inbound_sms"
    assert fake_db.call_logs.docs == []


def test_ghl_inbound_sms_rejects_bad_signature(api, known_super, monkeypatch):
    priv = Ed25519PrivateKey.generate()
    pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("GHL_PUBLIC_KEY", pem)
    r = api.post("/api/webhooks/ghl/inbound-sms", json={
        "type": "InboundMessage", "messageType": "SMS",
        "from": "+19045550101", "body": "hi",
    })
    assert r.status_code == 401


def test_ghl_inbound_sms_accepts_valid_signature(api, known_super, monkeypatch, fake_db):
    priv = Ed25519PrivateKey.generate()
    pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("GHL_PUBLIC_KEY", pem)
    monkeypatch.setattr(server, "_chat_with_context", _fake_chat)
    payload = {
        "type": "InboundMessage",
        "messageType": "SMS",
        "from": "+19045550101",
        "to": "+12295857126",
        "body": "hi from site",
        "messageId": "sig_ok",
        "direction": "inbound",
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = base64.b64encode(priv.sign(raw)).decode()
    r = api.post(
        "/api/webhooks/ghl/inbound-sms",
        content=raw,
        headers={"Content-Type": "application/json", "x-ghl-signature": sig},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    # sanity: helper agrees
    assert ghl_signature_ok(raw, sig) == (True, True)


def test_twilio_form_webhook_still_xml(api, known_super, monkeypatch):
    monkeypatch.setattr(server, "_chat_with_context", _fake_chat)
    r = api.post(
        "/api/webhooks/twilio/sms",
        data={"From": "+19045550101", "Body": "change order extra work", "To": "+12295857126"},
    )
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<?xml" in r.text and "<Response>" in r.text and "<Message>" in r.text
