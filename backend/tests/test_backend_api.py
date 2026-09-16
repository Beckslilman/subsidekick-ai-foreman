"""Backend API tests for SubSidekick foreman app.

Requires ALLOW_DEV_LOGIN=1 on the target backend (demo login is off by default).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://sidekick-app-build.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

TOKEN = None
USER = None


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


# ---------- Auth ----------
def test_01_dev_login():
    global TOKEN, USER
    r = session.post(f"{API}/auth/dev-login")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "session_token" in data and data["session_token"]
    assert data["user"]["email"] == "demo@subsidekick.com"
    TOKEN = data["session_token"]
    USER = data["user"]


def test_02_auth_me():
    r = session.get(f"{API}/auth/me", headers=auth_headers())
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "demo@subsidekick.com"


def test_03_auth_me_missing_token_401():
    r = session.get(f"{API}/auth/me")
    assert r.status_code == 401


# ---------- Jobs ----------
def test_04_list_jobs():
    r = session.get(f"{API}/jobs", headers=auth_headers())
    assert r.status_code == 200, r.text
    jobs = r.json()
    assert isinstance(jobs, list) and len(jobs) >= 3
    names = [j["name"] for j in jobs]
    assert "Riverside Apartments" in names
    for j in jobs:
        assert "id" in j and "gc" in j and "progress" in j


def test_05_get_single_job():
    r = session.get(f"{API}/jobs", headers=auth_headers())
    job_id = r.json()[0]["id"]
    r2 = session.get(f"{API}/jobs/{job_id}", headers=auth_headers())
    assert r2.status_code == 200
    assert r2.json()["id"] == job_id


# ---------- Change Orders / Back Charges / Inspections ----------
def test_06_list_change_orders():
    r = session.get(f"{API}/change-orders", headers=auth_headers())
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) >= 2


def test_07_list_back_charges():
    r = session.get(f"{API}/back-charges", headers=auth_headers())
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) >= 1


def test_08_list_inspections():
    r = session.get(f"{API}/inspections", headers=auth_headers())
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) >= 2


# ---------- Digest ----------
def test_09_digest():
    r = session.get(f"{API}/digest", headers=auth_headers())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "action_required_count" in d
    assert "change_orders" in d and "back_charges" in d and "failed_inspections" in d
    assert d["action_required_count"] >= 1


# ---------- Briefing (LLM) ----------
def test_10_briefing_llm():
    r = session.get(f"{API}/briefing", headers=auth_headers(), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "summary" in d and len(d["summary"]) > 5
    assert "active_jobs" in d


# ---------- Chat: change order draft ----------
def test_11_chat_change_order_creates_draft():
    prev = session.get(f"{API}/change-orders", headers=auth_headers()).json()
    prev_count = len(prev)
    r = session.post(f"{API}/chat/send", headers=auth_headers(),
                     json={"content": "GC asked for extra work on the north wall — this is a change order."},
                     timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("action_hint") == "change_order_draft_created", d
    now = session.get(f"{API}/change-orders", headers=auth_headers()).json()
    assert len(now) == prev_count + 1


# ---------- Chat: back charge draft ----------
def test_12_chat_back_charge_creates_draft():
    prev = session.get(f"{API}/back-charges", headers=auth_headers()).json()
    prev_count = len(prev)
    r = session.post(f"{API}/chat/send", headers=auth_headers(),
                     json={"content": "GC is trying to hit us with a back charge for cleanup."},
                     timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("action_hint") == "back_charge_draft_created", d
    now = session.get(f"{API}/back-charges", headers=auth_headers()).json()
    assert len(now) == prev_count + 1


# ---------- PATCH change order ----------
def test_13_patch_change_order_approved():
    cos = session.get(f"{API}/change-orders", headers=auth_headers()).json()
    target = next((c for c in cos if c["status"] in ("draft", "pending")), cos[0])
    r = session.patch(f"{API}/change-orders/{target['id']}", headers=auth_headers(),
                      json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


# ---------- Voice TTS ----------
def test_14_voice_tts_returns_url():
    r = session.post(f"{API}/voice/tts", headers=auth_headers(),
                     json={"text": "Morning. This is a test."}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "key" in d and "url" in d
    assert d["url"].startswith("/api/voice/audio/") and d["url"].endswith(".mp3")
    # Fetch audio
    r2 = session.get(f"{BASE_URL}{d['url']}")
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").startswith("audio/mpeg")
    assert len(r2.content) > 100
