"""Iteration 4 backend tests - Office dashboard pivot (GHL/Twilio webhooks, team, calls, digest, briefing).

Preview backends that run these unsigned webhook + demo-login checks need:
  ALLOW_DEV_LOGIN=1
  TWILIO_SKIP_SIGNATURE_CHECK=1
(when TWILIO_AUTH_TOKEN / GHL_PUBLIC_KEY are configured). Production must leave those unset.
"""
import os, requests, pytest

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
       open("/app/frontend/.env").read().split("EXPO_PUBLIC_BACKEND_URL=")[1].split("\n")[0].strip()

@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/dev-login", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["session_token"]

@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Seed sanity ----------
def test_dev_login_seeds_user(token):
    assert token.startswith("dev_")


def test_jobs_seeded(hdr):
    r = requests.get(f"{BASE}/api/jobs", headers=hdr, timeout=15)
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) >= 3
    codes = {j["code"] for j in jobs}
    assert {"RIV", "OAK", "HIL"}.issubset(codes)


def test_team_seeded(hdr):
    r = requests.get(f"{BASE}/api/team", headers=hdr, timeout=15)
    assert r.status_code == 200
    team = r.json()
    assert len(team) >= 3
    phones = {t["phone_number"] for t in team}
    assert {"+19045550101", "+19045550102", "+19045550103"}.issubset(phones)


def test_digest_money_at_risk(hdr):
    r = requests.get(f"{BASE}/api/digest", headers=hdr, timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["change_orders", "back_charges", "schedule_changes", "jobs", "money_at_risk"]:
        assert k in d
    # Should be approx $4650 (3850 CO + 800 BC)
    assert d["money_at_risk"] >= 4600
    assert len(d["change_orders"]) >= 1
    assert len(d["back_charges"]) >= 1
    assert len(d["schedule_changes"]) >= 2


def test_briefing_counts(hdr):
    r = requests.get(f"{BASE}/api/briefing", headers=hdr, timeout=60)
    assert r.status_code == 200
    b = r.json()
    assert "summary" in b and isinstance(b["summary"], str)
    assert b["drafts_pending"] >= 1
    assert b["back_charges_open"] >= 1
    assert b["schedule_changes_open"] >= 2


def test_calls_seeded_desc(hdr):
    r = requests.get(f"{BASE}/api/calls", headers=hdr, timeout=15)
    assert r.status_code == 200
    calls = r.json()
    assert len(calls) >= 3
    # Sorted desc
    ts = [c["started_at"] for c in calls]
    assert ts == sorted(ts, reverse=True)


def test_schedule_changes_list(hdr):
    r = requests.get(f"{BASE}/api/schedule-changes", headers=hdr, timeout=15)
    assert r.status_code == 200
    assert len(r.json()) >= 2


# ---------- Team CRUD ----------
def test_team_crud(hdr):
    # Create
    r = requests.post(f"{BASE}/api/team", headers=hdr,
                      json={"name": "TEST_super", "phone_number": "+19045559999", "briefing_hour": 7, "briefing_minute": 0},
                      timeout=15)
    assert r.status_code == 200, r.text
    tm = r.json()
    assert tm["phone_number"] == "+19045559999"
    tm_id = tm["id"]
    # Patch
    r = requests.patch(f"{BASE}/api/team/{tm_id}", headers=hdr,
                      json={"name": "TEST_super_updated", "briefing_hour": 8}, timeout=15)
    assert r.status_code == 200
    assert r.json()["name"] == "TEST_super_updated"
    assert r.json()["briefing_hour"] == 8
    # Delete (soft)
    r = requests.delete(f"{BASE}/api/team/{tm_id}", headers=hdr, timeout=15)
    assert r.status_code == 200
    # Not returned anymore
    r = requests.get(f"{BASE}/api/team", headers=hdr, timeout=15)
    ids = [t["id"] for t in r.json()]
    assert tm_id not in ids


# ---------- Team briefing ----------
def test_team_briefing_and_trigger(hdr):
    r = requests.get(f"{BASE}/api/team", headers=hdr, timeout=15)
    tm_id = r.json()[0]["id"]
    r = requests.get(f"{BASE}/api/team/{tm_id}/briefing", headers=hdr, timeout=60)
    assert r.status_code == 200
    j = r.json()
    assert j["team_member_id"] == tm_id
    assert j["name"] and j["phone"] and j["briefing"]

    # Trigger briefing - Twilio blank => GHL Conversations or outbox
    r = requests.post(f"{BASE}/api/team/{tm_id}/trigger-briefing", headers=hdr, timeout=60)
    assert r.status_code == 200
    payload = r.json()
    assert payload["delivered_via"] in {"outbox", "ghl", "twilio"}
    # New call log added
    r = requests.get(f"{BASE}/api/calls", headers=hdr, timeout=15)
    calls = r.json()
    latest = calls[0]
    assert latest["channel"] == "sms"
    assert latest["direction"] == "outbound"
    assert latest["team_member_id"] == tm_id


# ---------- Money item PATCH statuses ----------
def test_change_order_approve(hdr):
    r = requests.get(f"{BASE}/api/change-orders", headers=hdr, timeout=15)
    co = r.json()[0]
    r = requests.patch(f"{BASE}/api/change-orders/{co['id']}", headers=hdr,
                      json={"status": "approved"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_back_charge_resolve(hdr):
    r = requests.get(f"{BASE}/api/back-charges", headers=hdr, timeout=15)
    bc = r.json()[0]
    r = requests.patch(f"{BASE}/api/back-charges/{bc['id']}", headers=hdr,
                      json={"status": "resolved"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"


def test_schedule_change_confirm(hdr):
    r = requests.get(f"{BASE}/api/schedule-changes", headers=hdr, timeout=15)
    sc = r.json()[0]
    r = requests.patch(f"{BASE}/api/schedule-changes/{sc['id']}", headers=hdr,
                      json={"status": "confirmed"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


# ---------- Twilio SMS webhook ----------
def test_twilio_sms_known_number_creates_draft(hdr):
    # Count COs first
    before = len(requests.get(f"{BASE}/api/change-orders", headers=hdr, timeout=15).json())
    r = requests.post(f"{BASE}/api/webhooks/twilio/sms",
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data="From=%2B19045550101&Body=GC+added+extra+work+on+east+wall+change+order&To=%2B12295857126",
                      timeout=60)
    assert r.status_code == 200
    assert "<?xml" in r.text and "<Response>" in r.text and "<Message>" in r.text
    # New CO draft should exist
    after = len(requests.get(f"{BASE}/api/change-orders", headers=hdr, timeout=15).json())
    assert after == before + 1
    # Latest call log is inbound SMS
    calls = requests.get(f"{BASE}/api/calls", headers=hdr, timeout=15).json()
    latest = calls[0]
    assert latest["channel"] == "sms"
    assert latest["direction"] == "inbound"


def test_twilio_sms_unknown_number(hdr):
    r = requests.post(f"{BASE}/api/webhooks/twilio/sms",
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data="From=%2B15550001111&Body=hi&To=%2B12295857126",
                      timeout=15)
    assert r.status_code == 200
    assert "<Response>" in r.text and "<Message>" in r.text
    assert "isn't set up" in r.text


# ---------- GHL webhook ----------
def test_ghl_voice_webhook_creates_schedule_and_idempotent(hdr):
    call_id = "test-ghl-iter4-1"
    body = {
        "data": {
            "callId": call_id,
            "from": "+19045550102",
            "to": "+12295857126",
            "transcript": "GC pushed inspection to Thursday",
            "summary": "Schedule change",
            "extracted": {
                "schedule_changes": [
                    {"job_name": "Hillcrest", "description": "Inspection pushed to Thursday"}
                ]
            },
        }
    }
    before = len(requests.get(f"{BASE}/api/schedule-changes", headers=hdr, timeout=15).json())
    r = requests.post(f"{BASE}/api/webhooks/ghl/voice-ai", json=body, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert len(j["drafts_created"]) == 1
    after = len(requests.get(f"{BASE}/api/schedule-changes", headers=hdr, timeout=15).json())
    assert after == before + 1
    # Call log has ghl_call_id
    calls = requests.get(f"{BASE}/api/calls", headers=hdr, timeout=15).json()
    assert any(c.get("ghl_call_id") == call_id for c in calls)

    # Idempotent replay
    r2 = requests.post(f"{BASE}/api/webhooks/ghl/voice-ai", json=body, timeout=30)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("duplicate") is True
    after2 = len(requests.get(f"{BASE}/api/schedule-changes", headers=hdr, timeout=15).json())
    assert after2 == after  # no new draft


# ---------- Settings ----------
def test_settings_patch_ghl_and_twilio(hdr):
    r = requests.patch(f"{BASE}/api/settings", headers=hdr,
                      json={"ghl_access_token": "test_ghl_tok_abc",
                            "ghl_location_id": "loc_xyz",
                            "twilio_from_number": "+12295857126"},
                      timeout=15)
    assert r.status_code == 200
    u = r.json()
    assert u["ghl_access_token_set"] is True
    assert u["ghl_location_id"] == "loc_xyz"
