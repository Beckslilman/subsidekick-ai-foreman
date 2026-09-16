"""Webhook and demo-login hardening helpers.

Live Twilio/GHL credentials stay in process env (Deployment Secrets).
These helpers do not read or persist SID/token values from the Settings form.
"""
from __future__ import annotations

import base64
import os
from typing import Mapping, Optional
from xml.sax.saxutils import escape as xml_escape

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}
PROD_VALUES = {"production", "prod"}


def env_flag(name: str, default: str = "") -> Optional[bool]:
    """Return True/False for an explicit env flag, or None if unset/unrecognized."""
    raw = os.environ.get(name, default)
    if raw is None:
        return None
    val = str(raw).strip().lower()
    if val in TRUTHY:
        return True
    if val in FALSY:
        return False
    return None


def env_truthy(name: str) -> bool:
    return env_flag(name) is True


def is_production() -> bool:
    for key in ("ENVIRONMENT", "APP_ENV", "ENV", "NODE_ENV"):
        val = os.environ.get(key, "").strip().lower()
        if val:
            return val in PROD_VALUES
    return False


def dev_login_allowed() -> bool:
    """Demo login is off unless ALLOW_DEV_LOGIN is explicitly 1/true/yes/on."""
    return env_truthy("ALLOW_DEV_LOGIN")


def twilio_skip_signature_check() -> bool:
    return env_truthy("TWILIO_SKIP_SIGNATURE_CHECK")


def twilio_auth_token() -> str:
    return (os.environ.get("TWILIO_AUTH_TOKEN") or "").strip()


def twilio_signature_required() -> bool:
    """Validate Twilio signatures unless an explicit preview bypass is set.

    Fail closed when TWILIO_AUTH_TOKEN is set, or in production (even if the
    token is missing — unsigned webhooks must not be processed live).
    """
    if twilio_skip_signature_check():
        return False
    if twilio_auth_token():
        return True
    return is_production()


def public_request_url(scheme_host_path: str, forwarded_proto: Optional[str] = None,
                       forwarded_host: Optional[str] = None, path: Optional[str] = None,
                       query: Optional[str] = None, override: Optional[str] = None) -> str:
    """Rebuild the URL Twilio signed (https public URL, not the internal http hop)."""
    if override:
        return override.strip()
    if forwarded_proto and forwarded_host and path is not None:
        url = f"{forwarded_proto}://{forwarded_host}{path}"
        if query:
            url += f"?{query}"
        return url
    return scheme_host_path


def twilio_request_url_from_request(request, override: Optional[str] = None) -> str:
    env_override = override if override is not None else (os.environ.get("TWILIO_WEBHOOK_URL") or "").strip() or None
    xf_proto = request.headers.get("x-forwarded-proto")
    xf_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return public_request_url(
        str(request.url),
        forwarded_proto=xf_proto,
        forwarded_host=xf_host,
        path=request.url.path,
        query=request.url.query or None,
        override=env_override,
    )


def verify_twilio_signature(url: str, params: Mapping[str, str], signature: Optional[str],
                            auth_token: Optional[str] = None) -> bool:
    token = (auth_token if auth_token is not None else twilio_auth_token()).strip()
    if not token or not signature or not url:
        return False
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(token)
        return bool(validator.validate(url, dict(params), signature))
    except Exception:
        return False


def escape_twiml_text(text: Optional[str]) -> str:
    """Escape LLM/user text before interpolating into TwiML XML element content."""
    if text is None:
        return ""
    cleaned = str(text).replace("\x00", "")
    return xml_escape(cleaned, {"'": "&apos;", '"': "&quot;"})


def render_sms_twiml(message: str) -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<Response><Message>{escape_twiml_text(message)}</Message></Response>"
    )


def ghl_public_key_configured() -> bool:
    return bool((os.environ.get("GHL_PUBLIC_KEY") or "").strip())


def load_ghl_public_key(pem: Optional[str] = None):
    raw = pem if pem is not None else (os.environ.get("GHL_PUBLIC_KEY") or "")
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        from cryptography.hazmat.primitives import serialization
        return serialization.load_pem_public_key(raw.replace("\\n", "\n").encode())
    except Exception:
        return False  # configured but unusable — fail closed


def verify_ghl_signature(raw_body: bytes, signature_header: Optional[str], public_key=None) -> bool:
    key = public_key if public_key is not None else load_ghl_public_key()
    if not key or key is False or not signature_header:
        return False
    try:
        sig = base64.b64decode(signature_header, validate=True)
        key.verify(sig, raw_body)
        return True
    except Exception:
        return False


def ghl_signature_ok(raw_body: bytes, signature_header: Optional[str]) -> tuple[bool, bool]:
    """Return (enforced, verified).

    When GHL_PUBLIC_KEY is set, enforced is True and the caller must reject
    unverified requests. When unset, enforced is False (preview/dev).
    """
    pem = (os.environ.get("GHL_PUBLIC_KEY") or "").strip()
    if not pem:
        return False, False
    key = load_ghl_public_key(pem)
    if key is None or key is False:
        return True, False
    return True, verify_ghl_signature(raw_body, signature_header, public_key=key)
