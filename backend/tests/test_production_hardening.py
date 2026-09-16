"""Endpoint tests for production hardening (signatures, TwiML, dedupe, demo-login).

Uses an in-memory fake Mongo and Twilio RequestValidator — no live Twilio.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "subsidekick_hardening_test")
os.environ["SKIP_BACKGROUND_JOBS"] = "1"
for _k in (
    "TWILIO_AUTH_TOKEN",
    "TWILIO_SKIP_SIGNATURE_CHECK",
    "GHL_PUBLIC_KEY",
    "ALLOW_DEV_LOGIN",
    "ENVIRONMENT",
    "APP_ENV",
    "ENV",
    "NODE_ENV",
    "TWILIO_WEBHOOK_URL",
):
    os.environ.pop(_k, None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import json
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError
from twilio.request_validator import RequestValidator

import server


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
        return type("R", (), {"inserted_id": doc.get("id") or doc.get("message_sid")})()

    async def insert_many(self, docs):
        for doc in docs:
            await self.insert_one(doc)
        return type("R", (), {"inserted_ids": [d.get("id") for d in docs]})()

    async def update_one(self, query, update):
        matched = 0
        for d in self.docs:
            if self._match(d, query):
                matched += 1
                d.update(update.get("$set") or {})
                for k in (update.get("$unset") or {}):
                    d.pop(k, None)
                break
        return type("R", (), {"matched_count": matched})()

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
        self.uploads = FakeCollection()
        self.crew_assignments = FakeCollection()
        self.checkin_sessions = FakeCollection()
        self.inspections = FakeCollection()

    def __getattr__(self, name):
        coll = FakeCollection()
        setattr(self, name, coll)
        return coll


TWILIO_TOKEN = "hardening_test_token"
SMS_PATH = "/api/webhooks/twilio/sms"


def _sign(url, params, token=TWILIO_TOKEN):
    return RequestValidator(token).compute_signature(url, params)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(server, "db", db)
    return db


@pytest.fixture
def client(fake_db):
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
        "ai_message": {"content": "Logged DRAFT. Extra: 3 < 4 & 5 > 2. </Message><Message>injected</Message>"},
        "action_hint": "change_order_draft_created",
        "route_hint": None,
        "extracted_drafts": ["co_from_sms"],
    }


def test_dev_login_forbidden_by_default(client):
    r = client.post("/api/auth/dev-login")
    assert r.status_code == 403
    assert "disabled" in r.json()["detail"].lower()


def test_dev_login_allowed_when_flag_set(client, fake_db, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_LOGIN", "1")
    r = client.post("/api/auth/dev-login")
    assert r.status_code == 200
    body = r.json()
    assert body["session_token"].startswith("dev_")
    assert body["user"]["email"] == "demo@subsidekick.com"


def test_twilio_unsigned_rejected_when_token_set(client, known_super, monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TWILIO_TOKEN)
    r = client.post(SMS_PATH, data={"From": "+19045550101", "Body": "hi", "To": "+12295857126"})
    assert r.status_code == 403
    assert len(server.db.call_logs.docs) == 0


def test_twilio_invalid_signature_rejected(client, known_super, monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TWILIO_TOKEN)
    r = client.post(
        SMS_PATH,
        data={"From": "+19045550101", "Body": "hi", "To": "+12295857126"},
        headers={"X-Twilio-Signature": "aaaa"},
    )
    assert r.status_code == 403


def test_twilio_valid_signature_accepted_and_escapes_twiml(client, known_super, monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TWILIO_TOKEN)
    monkeypatch.setattr(server, "_chat_with_context", _fake_chat)
    params = {
        "From": "+19045550101",
        "Body": "GC added extra work change order",
        "To": "+12295857126",
        "MessageSid": "SM111",
    }
    url = f"http://testserver{SMS_PATH}"
    sig = _sign(url, params)
    r = client.post(SMS_PATH, data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200
    assert "<?xml" in r.text and "<Response>" in r.text
    assert r.text.count("<Message>") == 1
    assert "&amp;" in r.text and "&lt;" in r.text and "&gt;" in r.text
    assert "</Message><Message>injected" not in r.text
    assert len(server.db.call_logs.docs) == 1
    log = server.db.call_logs.docs[0]
    assert log["extracted_drafts"] == ["co_from_sms"]
    assert log["channel"] == "sms"


def test_twilio_skip_flag_allows_unsigned_preview(client, known_super, monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TWILIO_TOKEN)
    monkeypatch.setenv("TWILIO_SKIP_SIGNATURE_CHECK", "1")
    monkeypatch.setattr(server, "_chat_with_context", _fake_chat)
    r = client.post(
        SMS_PATH,
        data={"From": "+19045550101", "Body": "yo", "To": "+12295857126", "MessageSid": "SM-skip"},
    )
    assert r.status_code == 200
    assert "<Response>" in r.text


def test_twilio_messagesid_dedupe(client, known_super, monkeypatch):
    monkeypatch.setenv("TWILIO_SKIP_SIGNATURE_CHECK", "1")
    monkeypatch.setattr(server, "_chat_with_context", _fake_chat)
    data = {
        "From": "+19045550101",
        "Body": "extra work change order",
        "To": "+12295857126",
        "MessageSid": "SM-dup",
    }
    r1 = client.post(SMS_PATH, data=data)
    r2 = client.post(SMS_PATH, data=data)
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(server.db.call_logs.docs) == 1
    assert "<Response>" in r2.text


def test_twilio_calllog_attaches_real_extracted_draft_ids(client, known_super, monkeypatch):
    """Parity with GHL: inbound SMS CallLog.extracted_drafts gets IDs from _chat_with_context."""
    monkeypatch.setenv("TWILIO_SKIP_SIGNATURE_CHECK", "1")
    r = client.post(
        SMS_PATH,
        data={
            "From": "+19045550101",
            "Body": "GC added extra work on east wall change order",
            "To": "+12295857126",
            "MessageSid": "SM-drafts",
        },
    )
    assert r.status_code == 200
    assert len(server.db.change_orders.docs) == 1
    co_id = server.db.change_orders.docs[0]["id"]
    assert server.db.change_orders.docs[0]["status"] == "draft"
    log = server.db.call_logs.docs[0]
    assert log["extracted_drafts"] == [co_id]
    assert log["channel"] == "sms"


def test_ghl_unsigned_rejected_when_key_set(client, monkeypatch):
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("GHL_PUBLIC_KEY", pem)
    r = client.post("/api/webhooks/ghl/voice-ai", json={"data": {"callId": "c-unauth"}})
    assert r.status_code == 401
    assert server.db.ghl_events.docs == []
    assert server.db.call_logs.docs == []


def test_ghl_valid_signature_accepted(client, known_super, monkeypatch):
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("GHL_PUBLIC_KEY", pem)
    payload = {
        "data": {
            "callId": "c-ok-1",
            "from": "+19045550101",
            "to": "+12295857126",
            "transcript": "GC pushed inspection to Thursday",
            "extracted": {
                "schedule_changes": [{"job_name": "Riverstone", "description": "Inspection Thursday"}]
            },
        }
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = base64.b64encode(private.sign(raw)).decode()
    r = client.post(
        "/api/webhooks/ghl/voice-ai",
        content=raw,
        headers={"Content-Type": "application/json", "X-GHL-Signature": sig},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["signature_verified"] is True
    assert len(body["drafts_created"]) == 1
    assert server.db.call_logs.docs[0]["extracted_drafts"] == body["drafts_created"]


def test_settings_does_not_persist_twilio_secrets(client, fake_db, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_LOGIN", "1")
    login = client.post("/api/auth/dev-login")
    token = login.json()["session_token"]
    r = client.patch(
        "/api/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ghl_access_token": "super-secret-pit",
            "ghl_location_id": "loc_xyz",
            "twilio_account_sid": "ACxxxxxxxx",
            "twilio_auth_token": "secret-token-value",
            "twilio_from_number": "+12295857126",
        },
    )
    assert r.status_code == 200, r.text
    user = fake_db.users.docs[0]
    assert "twilio_auth_token" not in user
    assert "twilio_account_sid" not in user
    assert "ghl_access_token_encrypted" not in user
    assert "ghl_access_token" not in user
    assert user.get("twilio_account_sid_set") is True
    assert user.get("twilio_auth_token_set") is True
    assert user.get("ghl_access_token_set") is True
    assert user.get("ghl_location_id") == "loc_xyz"
    assert "secret-token-value" not in str(user)
    assert r.json()["ghl_access_token_set"] is True
    assert r.json()["ghl_location_id"] == "loc_xyz"
