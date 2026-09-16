"""Unit tests for webhook hardening — no live Twilio, no Mongo required."""
import base64
import os
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from twilio.request_validator import RequestValidator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import webhook_security as ws


TWILIO_TOKEN = "test_twilio_auth_token_not_real"
TWILIO_URL = "https://example.com/api/webhooks/twilio/sms"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "TWILIO_AUTH_TOKEN",
        "TWILIO_SKIP_SIGNATURE_CHECK",
        "TWILIO_WEBHOOK_URL",
        "GHL_PUBLIC_KEY",
        "ALLOW_DEV_LOGIN",
        "ENVIRONMENT",
        "APP_ENV",
        "ENV",
        "NODE_ENV",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_escape_twiml_breaks_message_injection():
    payload = '</Message><Message>pwned</Message>'
    escaped = ws.escape_twiml_text(payload)
    assert "<Message>" not in escaped
    assert "&lt;/Message&gt;" in escaped
    xml = ws.render_sms_twiml(payload)
    assert xml.count("<Message>") == 1
    assert "pwned" in xml
    assert "</Message><Message>pwned" not in xml


def test_escape_twiml_amp_lt_gt_and_quotes():
    escaped = ws.escape_twiml_text('A & B < C > D "E" \'F\'')
    assert "&amp;" in escaped
    assert "&lt;" in escaped
    assert "&gt;" in escaped
    assert "&quot;" in escaped
    assert "&apos;" in escaped
    assert "&" not in escaped.replace("&amp;", "").replace("&lt;", "").replace("&gt;", "").replace("&quot;", "").replace("&apos;", "")


def test_twilio_signature_accept_and_reject():
    params = {"From": "+19045550101", "Body": "extra work change order", "To": "+12295857126", "MessageSid": "SMabc"}
    validator = RequestValidator(TWILIO_TOKEN)
    good_sig = validator.compute_signature(TWILIO_URL, params)
    assert ws.verify_twilio_signature(TWILIO_URL, params, good_sig, auth_token=TWILIO_TOKEN) is True
    assert ws.verify_twilio_signature(TWILIO_URL, params, "bogus", auth_token=TWILIO_TOKEN) is False
    assert ws.verify_twilio_signature(TWILIO_URL, params, None, auth_token=TWILIO_TOKEN) is False
    assert ws.verify_twilio_signature(TWILIO_URL, params, good_sig, auth_token="wrong-token") is False
    tampered = dict(params, Body="not in the bid — send invoice now")
    assert ws.verify_twilio_signature(TWILIO_URL, tampered, good_sig, auth_token=TWILIO_TOKEN) is False


def test_twilio_signature_required_token_set_unless_skip(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TWILIO_TOKEN)
    assert ws.twilio_signature_required() is True
    monkeypatch.setenv("TWILIO_SKIP_SIGNATURE_CHECK", "1")
    assert ws.twilio_signature_required() is False


def test_twilio_signature_required_production_fail_closed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert ws.twilio_auth_token() == ""
    assert ws.twilio_signature_required() is True
    monkeypatch.setenv("TWILIO_SKIP_SIGNATURE_CHECK", "true")
    assert ws.twilio_signature_required() is False


def test_twilio_signature_not_required_in_dev_without_token():
    assert ws.twilio_signature_required() is False


def test_dev_login_off_by_default_on_with_flag(monkeypatch):
    assert ws.dev_login_allowed() is False
    monkeypatch.setenv("ALLOW_DEV_LOGIN", "1")
    assert ws.dev_login_allowed() is True
    monkeypatch.setenv("ALLOW_DEV_LOGIN", "true")
    assert ws.dev_login_allowed() is True
    monkeypatch.setenv("ALLOW_DEV_LOGIN", "0")
    assert ws.dev_login_allowed() is False


def test_ghl_signature_accept_and_reject_when_key_set(monkeypatch):
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("GHL_PUBLIC_KEY", pem)
    body = b'{"data":{"callId":"c1","transcript":"ok"}}'
    sig = base64.b64encode(private.sign(body)).decode()
    enforced, verified = ws.ghl_signature_ok(body, sig)
    assert enforced is True
    assert verified is True
    enforced_bad, verified_bad = ws.ghl_signature_ok(body, base64.b64encode(b"nope" + b"0" * 60).decode())
    assert enforced_bad is True
    assert verified_bad is False
    enforced_missing, verified_missing = ws.ghl_signature_ok(body, None)
    assert enforced_missing is True
    assert verified_missing is False


def test_ghl_not_enforced_when_key_unset():
    body = b"{}"
    enforced, verified = ws.ghl_signature_ok(body, None)
    assert enforced is False
    assert verified is False


def test_public_request_url_prefers_override_then_forwarded():
    assert ws.public_request_url("http://internal/x", override="https://public.example/hook") == "https://public.example/hook"
    rebuilt = ws.public_request_url(
        "http://internal/api/webhooks/twilio/sms",
        forwarded_proto="https",
        forwarded_host="app.example.com",
        path="/api/webhooks/twilio/sms",
        query=None,
    )
    assert rebuilt == "https://app.example.com/api/webhooks/twilio/sms"
