"""Iteration 3 backend tests: settings, recovery SMS, chat kickoff, dispatch editor."""
import os
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{BASE_URL}/api/auth/dev-login", timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["session_token"]
    return {"headers": {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, "token": tok}


# ---------- Settings ----------
class TestSettings:
    def test_patch_phone_and_opt_in(self, auth):
        r = requests.patch(f"{BASE_URL}/api/settings",
                           json={"phone_number": "+15551234567", "sms_opt_in": True},
                           headers=auth["headers"], timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["phone_number"] == "+15551234567"
        assert data["sms_opt_in"] is True

    def test_patch_invalid_phone_rejects(self, auth):
        r = requests.patch(f"{BASE_URL}/api/settings",
                           json={"phone_number": "123"},
                           headers=auth["headers"], timeout=15)
        assert r.status_code == 400


# ---------- Recovery ----------
class TestRecovery:
    def test_preview_contains_5050_and_phone(self, auth):
        # Ensure phone is on file first
        requests.patch(f"{BASE_URL}/api/settings",
                       json={"phone_number": "+15551234567", "sms_opt_in": True},
                       headers=auth["headers"], timeout=15)
        r = requests.get(f"{BASE_URL}/api/recovery/preview", headers=auth["headers"], timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "$5,050" in data["body"], f"Body did not contain $5,050: {data['body']}"
        assert data["phone_number"] == "+15551234567"

    def test_send_uses_outbox_when_twilio_blank(self, auth):
        r = requests.post(f"{BASE_URL}/api/recovery/send", headers=auth["headers"], timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Twilio-blank preview used to always outbox. With GHL Conversations fallback,
        # delivery is ghl when GHL_ACCESS_TOKEN + GHL_LOCATION_ID are set.
        assert data["delivered_via"] in {"outbox", "ghl", "twilio"}

    def test_send_400_when_no_phone(self, auth):
        # Clear phone
        requests.patch(f"{BASE_URL}/api/settings",
                       json={"phone_number": ""},
                       headers=auth["headers"], timeout=15)
        r = requests.post(f"{BASE_URL}/api/recovery/send", headers=auth["headers"], timeout=15)
        assert r.status_code == 400
        # Restore phone for later tests
        requests.patch(f"{BASE_URL}/api/settings",
                       json={"phone_number": "+15551234567", "sms_opt_in": True},
                       headers=auth["headers"], timeout=15)


# ---------- Chat kickoff ----------
class TestChatKickoff:
    def test_wrap_it_up_sets_route_hint(self, auth):
        r = requests.post(f"{BASE_URL}/api/chat/send",
                          json={"content": "wrap it up for the day"},
                          headers=auth["headers"], timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("route_hint") == "/checkin"
        assert data.get("action_hint") == "start_checkin"

    def test_both_keywords_route_hint_still_present(self, auth):
        r = requests.post(f"{BASE_URL}/api/chat/send",
                          json={"content": "change order added and wrap it up"},
                          headers=auth["headers"], timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("route_hint") == "/checkin"


# ---------- Dispatch editor ----------
class TestDispatchEditor:
    def _get_fresh(self, auth):
        r = requests.get(f"{BASE_URL}/api/dispatch", headers=auth["headers"], timeout=15)
        assert r.status_code == 200
        crews = r.json()["crews"]
        assigns = [a for c in crews for a in c["assignments"]]
        assert assigns
        return assigns

    def _get_jobs(self, auth):
        r = requests.get(f"{BASE_URL}/api/jobs", headers=auth["headers"], timeout=15)
        assert r.status_code == 200
        return r.json()

    def test_patch_job_updates_name(self, auth):
        assigns = self._get_fresh(auth)
        target = assigns[0]
        jobs = self._get_jobs(auth)
        other = next(j for j in jobs if j["id"] != target["job_id"])
        r = requests.patch(f"{BASE_URL}/api/dispatch/{target['id']}",
                           json={"job_id": other["id"]},
                           headers=auth["headers"], timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["job_id"] == other["id"]
        assert data["job_name"] == other["name"]

    def test_patch_crew(self, auth):
        assigns = self._get_fresh(auth)
        target = assigns[0]
        r = requests.patch(f"{BASE_URL}/api/dispatch/{target['id']}",
                           json={"crew": "Crew C"},
                           headers=auth["headers"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["crew"] == "Crew C"

    def test_patch_unknown_job_404(self, auth):
        assigns = self._get_fresh(auth)
        target = assigns[0]
        r = requests.patch(f"{BASE_URL}/api/dispatch/{target['id']}",
                           json={"job_id": "job_does_not_exist_xyz"},
                           headers=auth["headers"], timeout=15)
        assert r.status_code == 404

    def test_patch_unknown_dispatch_404(self, auth):
        r = requests.patch(f"{BASE_URL}/api/dispatch/dsp_missing_xyz",
                           json={"crew": "Crew C"},
                           headers=auth["headers"], timeout=15)
        assert r.status_code == 404

    def test_delete_then_delete_again(self, auth):
        # Create a fresh assignment so we don't disturb others irreversibly
        jobs = self._get_jobs(auth)
        j = jobs[0]
        from datetime import datetime, timedelta, timezone
        d = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
        r = requests.post(f"{BASE_URL}/api/dispatch",
                          json={"crew": "TEST_delete_crew", "job_id": j["id"], "date": d, "notes": "TEST"},
                          headers=auth["headers"], timeout=15)
        assert r.status_code == 200
        aid = r.json()["id"]
        r1 = requests.delete(f"{BASE_URL}/api/dispatch/{aid}", headers=auth["headers"], timeout=15)
        assert r1.status_code == 200
        r2 = requests.delete(f"{BASE_URL}/api/dispatch/{aid}", headers=auth["headers"], timeout=15)
        assert r2.status_code == 404


# ---------- Scheduler ----------
class TestScheduler:
    def test_scheduler_log_present(self):
        # Check backend log for scheduler start line
        try:
            with open("/var/log/supervisor/backend.err.log", "r") as f:
                content = f.read()
        except FileNotFoundError:
            content = ""
        try:
            with open("/var/log/supervisor/backend.out.log", "r") as f:
                content += f.read()
        except FileNotFoundError:
            pass
        assert "Weekly recovery scheduler started" in content, "Scheduler log line not found"
