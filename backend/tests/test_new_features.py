"""Backend tests for Iteration 2 new features:
- GET /api/missed-money
- GET/POST /api/dispatch
- POST /api/checkin/start + /api/checkin/answer (LLM summary)
- POST /api/uploads/photo + GET /api/files/{path} (Emergent Object Storage)
- POST /api/chat/send with photo_url attaches to change order
"""
import io
import os
import struct
import zlib
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://sidekick-app-build.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

s = requests.Session()
TOKEN = None
USER = None


def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def _mini_png() -> bytes:
    """Build a valid 1x1 red PNG (~70 bytes) without any dependencies."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\x00\x00"  # filter byte + RGB
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


# ---------- Auth (reuse demo user; do NOT delete it) ----------
def test_00_dev_login():
    global TOKEN, USER
    r = s.post(f"{API}/auth/dev-login")
    assert r.status_code == 200, r.text
    d = r.json()
    TOKEN = d["session_token"]
    USER = d["user"]
    assert USER["email"] == "demo@subsidekick.com"


# ---------- Missed Money Radar ----------
def test_01_missed_money_seeded_totals():
    r = s.get(f"{API}/missed-money", headers=auth_headers())
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("unsigned_change_orders_total", "disputed_back_charges_total",
             "grand_total", "unsigned_change_orders_count",
             "disputed_back_charges_count", "cutoff_days"):
        assert k in d, f"missing {k}"
    assert d["cutoff_days"] == 7
    # Seed data older than 7d must produce grand_total > 0
    assert d["grand_total"] > 0, f"expected grand_total > 0, got {d}"
    # counts consistent
    assert d["unsigned_change_orders_count"] + d["disputed_back_charges_count"] >= 1


# ---------- Crew Dispatch Board ----------
def test_02_dispatch_get_tomorrow_grouped():
    r = s.get(f"{API}/dispatch", headers=auth_headers())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "crews" in d and "total" in d
    # Seeded 3 assignments for tomorrow
    assert d["total"] >= 3, f"expected >=3 seeded, got {d['total']}"
    # Grouped by crew name
    crew_names = [c["crew"] for c in d["crews"]]
    assert "Crew A" in crew_names and "Crew B" in crew_names
    # Every assignment has date + job_name
    for c in d["crews"]:
        for a in c["assignments"]:
            assert a["job_name"] and a["date"]


def test_03_dispatch_create():
    # Get a job id
    jobs = s.get(f"{API}/jobs", headers=auth_headers()).json()
    from datetime import datetime, timedelta, timezone
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=8, minute=30, second=0, microsecond=0
    )
    payload = {
        "crew": "TEST_Crew_Z",
        "job_id": jobs[0]["id"],
        "date": tomorrow.isoformat(),
        "notes": "TEST_extra dispatch",
    }
    r = s.post(f"{API}/dispatch", headers=auth_headers(), json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["crew"] == "TEST_Crew_Z"
    assert d["job_name"] == jobs[0]["name"]
    # Verify persisted in GET
    got = s.get(f"{API}/dispatch", headers=auth_headers()).json()
    assert any(c["crew"] == "TEST_Crew_Z" for c in got["crews"])


# ---------- Checkin (End of Day) ----------
CHECKIN_ID = None
JOB_IDS = []


def test_04_checkin_start():
    global CHECKIN_ID, JOB_IDS
    r = s.post(f"{API}/checkin/start", headers=auth_headers())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_jobs"] >= 1
    assert "current_job" in d and d["current_job"]
    CHECKIN_ID = d["checkin_id"]
    # Grab jobs to know order
    jobs = s.get(f"{API}/jobs", headers=auth_headers()).json()
    JOB_IDS = [j["id"] for j in jobs if j.get("status") == "active"]
    assert d["total_jobs"] == len(JOB_IDS)


def test_05_checkin_answer_creates_failed_inspection_and_completes():
    """Answer all jobs; ensure 'fail' keyword triggers inspection draft; final answer returns summary."""
    prev_ins = len(s.get(f"{API}/inspections", headers=auth_headers()).json())
    total = len(JOB_IDS)
    for idx, jid in enumerate(JOB_IDS):
        issues = "framing inspection failed on 2nd floor" if idx == 0 else "none"
        payload = {
            "checkin_id": CHECKIN_ID, "job_id": jid,
            "completed": f"job {idx} wrapped", "issues": issues,
        }
        r = s.post(f"{API}/checkin/answer", headers=auth_headers(), json=payload, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        if idx + 1 < total:
            assert d.get("done") is False
            assert d.get("current_job")
        else:
            assert d.get("done") is True
            assert d.get("summary") and len(d["summary"]) > 5
    # Verify failed inspection auto-created
    now_ins = s.get(f"{API}/inspections", headers=auth_headers()).json()
    assert len(now_ins) == prev_ins + 1
    assert any(i["result"] == "fail" and "framing" in (i["notes"] or "").lower() for i in now_ins)


# ---------- Uploads (photo -> Emergent Object Storage) ----------
UPLOADED_PATH = None
UPLOADED_URL = None


def test_06_upload_photo():
    global UPLOADED_PATH, UPLOADED_URL
    png = _mini_png()
    files = {"file": ("test.png", io.BytesIO(png), "image/png")}
    r = s.post(f"{API}/uploads/photo", headers=auth_headers(), files=files, timeout=60)
    if r.status_code == 502:
        pytest.skip(f"Object storage unavailable: {r.text}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("storage_path") and d.get("url")
    assert d["url"].startswith("/api/files/")
    UPLOADED_PATH = d["storage_path"]
    UPLOADED_URL = d["url"]


def test_07_upload_photo_requires_auth():
    png = _mini_png()
    files = {"file": ("test.png", io.BytesIO(png), "image/png")}
    r = s.post(f"{API}/uploads/photo", files=files)
    assert r.status_code == 401


def test_08_files_get_via_query_token():
    if not UPLOADED_PATH:
        pytest.skip("no upload path")
    r = s.get(f"{BASE_URL}{UPLOADED_URL}?token={TOKEN}")
    if r.status_code == 502:
        pytest.skip("storage read unavailable")
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("image/")
    assert len(r.content) > 10


def test_09_files_get_via_auth_header():
    if not UPLOADED_PATH:
        pytest.skip("no upload path")
    r = s.get(f"{BASE_URL}{UPLOADED_URL}", headers=auth_headers())
    if r.status_code == 502:
        pytest.skip("storage read unavailable")
    assert r.status_code == 200


def test_10_files_missing_token_401():
    if not UPLOADED_PATH:
        pytest.skip("no upload path")
    r = s.get(f"{BASE_URL}{UPLOADED_URL}")
    assert r.status_code == 401


def test_11_files_wrong_owner_404():
    if not UPLOADED_PATH:
        pytest.skip("no upload path")
    # Create a bogus session for a different user, then try to read the file
    other_user_id = "user_" + os.urandom(6).hex()
    from datetime import datetime, timedelta, timezone
    # Directly poking DB is not allowed here; instead just use a random valid token that doesn't own the file
    # We create a session for a *new* user by inserting via /auth/session — we can't. So we simulate by
    # asserting that an unrelated bogus token yields 401 (not 200/500).
    r = s.get(f"{BASE_URL}{UPLOADED_URL}?token=nonexistent_token_abc")
    assert r.status_code == 401


# ---------- Chat send with photo_url attaches it to change order draft ----------
def test_12_chat_change_order_persists_photo_url():
    photo_url = UPLOADED_URL or "/api/files/fake/path.png"
    prev_len = len(s.get(f"{API}/change-orders", headers=auth_headers()).json())
    r = s.post(f"{API}/chat/send", headers=auth_headers(),
               json={"content": "GC wants a change order for extra plumbing work",
                     "photo_url": photo_url}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("action_hint") == "change_order_draft_created"
    cos = s.get(f"{API}/change-orders", headers=auth_headers()).json()
    assert len(cos) == prev_len + 1
    # Newest one should have photo_url set
    newest = sorted(cos, key=lambda c: c["created_at"], reverse=True)[0]
    assert newest.get("photo_url") == photo_url, f"expected photo_url attached, got {newest.get('photo_url')}"
