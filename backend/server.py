from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Request, Response, Query
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, io, base64, logging, tempfile, inspect, hashlib, requests, json
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Any
import uuid
from datetime import datetime, timedelta, timezone
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# --- Twilio ---
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID', '').strip()
TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '').strip()
TWILIO_FROM = os.environ.get('TWILIO_FROM_NUMBER', '').strip()

def _twilio_client():
    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        return None
    try:
        from twilio.rest import Client
        return Client(TWILIO_SID, TWILIO_TOKEN)
    except Exception:
        return None

def _send_sms_sync(to: str, body: str) -> dict:
    c = _twilio_client()
    if not c:
        return {"provider": "outbox", "to": to, "body": body}
    try:
        m = c.messages.create(from_=TWILIO_FROM, to=to, body=body)
        return {"provider": "twilio", "sid": m.sid, "to": to, "body": body}
    except Exception as e:
        return {"provider": "outbox", "to": to, "body": body, "error": str(e)}

# --- GHL ---
GHL_ACCESS_TOKEN = os.environ.get('GHL_ACCESS_TOKEN', '').strip()
GHL_LOCATION_ID = os.environ.get('GHL_LOCATION_ID', '').strip()
GHL_PUBLIC_KEY_PEM = os.environ.get('GHL_PUBLIC_KEY', '').strip()

def _load_ghl_key():
    if not GHL_PUBLIC_KEY_PEM:
        return None
    try:
        from cryptography.hazmat.primitives import serialization
        return serialization.load_pem_public_key(GHL_PUBLIC_KEY_PEM.replace("\\n", "\n").encode())
    except Exception:
        return None

_ghl_pubkey = _load_ghl_key()

def _verify_ghl_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    if not _ghl_pubkey or not signature_header:
        return False
    try:
        sig = base64.b64decode(signature_header, validate=True)
        _ghl_pubkey.verify(sig, raw_body)
        return True
    except Exception:
        return False

# --- Emergent Object Storage ---
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "subsidekick"
_storage_key: Optional[str] = None

def _init_storage_sync() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    r.raise_for_status()
    _storage_key = r.json()["storage_key"]
    return _storage_key

def _put_object_sync(path: str, data: bytes, ct: str) -> dict:
    k = _init_storage_sync()
    r = requests.put(f"{STORAGE_URL}/objects/{path}",
                     headers={"X-Storage-Key": k, "Content-Type": ct}, data=data, timeout=120)
    if r.status_code == 503:
        globals()["_storage_key"] = None
        k = _init_storage_sync()
        r = requests.put(f"{STORAGE_URL}/objects/{path}",
                         headers={"X-Storage-Key": k, "Content-Type": ct}, data=data, timeout=120)
    r.raise_for_status()
    return r.json()

def _get_object_sync(path: str) -> tuple[bytes, str]:
    k = _init_storage_sync()
    r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": k}, timeout=60)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")

# --- App ---
app = FastAPI()
api_router = APIRouter(prefix="/api")

def new_id(p="id"): return f"{p}_{uuid.uuid4().hex[:12]}"
def utcnow(): return datetime.now(timezone.utc)

# ---------------- Models ----------------
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    phone_number: Optional[str] = None
    sms_opt_in: bool = False
    ghl_access_token_set: bool = False
    ghl_location_id: Optional[str] = None
    twilio_configured: bool = False
    created_at: datetime = Field(default_factory=utcnow)

class SessionRequest(BaseModel):
    session_id: str

class SessionResponse(BaseModel):
    session_token: str
    user: User

class Job(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job"))
    user_id: str
    code: str = ""  # 3-letter code like RIV, OAK
    name: str
    gc: str
    address: str
    status: Literal["active", "on_hold", "completed"] = "active"
    crew: str = ""
    crew_size: int = 0
    progress: int = 0
    working_on: str = ""
    next_milestone: str = ""
    created_at: datetime = Field(default_factory=utcnow)

class TeamMember(BaseModel):
    id: str = Field(default_factory=lambda: new_id("tm"))
    user_id: str  # owner (office admin)
    name: str
    role: str = "Superintendent"
    phone_number: str
    timezone: str = "America/New_York"
    briefing_hour: int = 6
    briefing_minute: int = 30
    briefing_enabled: bool = True
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)

class TeamMemberCreate(BaseModel):
    name: str
    role: str = "Superintendent"
    phone_number: str
    timezone: str = "America/New_York"
    briefing_hour: int = 6
    briefing_minute: int = 30

class TeamMemberUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    phone_number: Optional[str] = None
    timezone: Optional[str] = None
    briefing_hour: Optional[int] = None
    briefing_minute: Optional[int] = None
    briefing_enabled: Optional[bool] = None
    active: Optional[bool] = None

class ChangeOrder(BaseModel):
    id: str = Field(default_factory=lambda: new_id("co"))
    user_id: str
    job_id: str
    job_name: str
    title: str = ""
    description: str
    ai_estimate: Optional[float] = None
    labor_hours: Optional[float] = None
    material_notes: Optional[str] = None
    amount: Optional[float] = None
    status: Literal["draft", "pending", "approved", "rejected"] = "draft"
    reported_by: str = "Field"
    reported_by_phone: Optional[str] = None
    photo_urls: List[str] = []
    voice_note_url: Optional[str] = None
    source: Literal["call", "sms", "manual", "chat"] = "manual"
    call_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

class BackCharge(BaseModel):
    id: str = Field(default_factory=lambda: new_id("bc"))
    user_id: str
    job_id: str
    job_name: str
    title: str = ""
    description: str
    amount: float
    status: Literal["draft", "disputed", "resolved"] = "draft"
    reported_by: str = "Field"
    reported_by_phone: Optional[str] = None
    photo_urls: List[str] = []
    voice_note_url: Optional[str] = None
    source: Literal["call", "sms", "manual", "chat"] = "manual"
    call_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

class Inspection(BaseModel):
    id: str = Field(default_factory=lambda: new_id("insp"))
    user_id: str
    job_id: str
    job_name: str
    inspection_type: str
    result: Literal["pass", "fail", "pending"] = "pending"
    notes: str = ""
    reschedule_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)

class ScheduleChange(BaseModel):
    id: str = Field(default_factory=lambda: new_id("sch"))
    user_id: str
    job_id: str
    job_name: str
    description: str
    old_date: Optional[datetime] = None
    new_date: Optional[datetime] = None
    status: Literal["draft", "notified", "confirmed"] = "draft"
    reported_by: str = "Field"
    reported_by_phone: Optional[str] = None
    source: Literal["call", "sms", "manual", "chat"] = "manual"
    call_id: Optional[str] = None
    notify_targets: List[str] = []
    created_at: datetime = Field(default_factory=utcnow)

class CallLog(BaseModel):
    id: str = Field(default_factory=lambda: new_id("call"))
    user_id: str
    direction: Literal["inbound", "outbound"]
    channel: Literal["voice", "sms"] = "voice"
    from_number: str = ""
    to_number: str = ""
    team_member_id: Optional[str] = None
    team_member_name: Optional[str] = None
    duration_sec: int = 0
    transcript: Optional[str] = None
    summary: Optional[str] = None
    ghl_call_id: Optional[str] = None
    extracted_drafts: List[str] = []  # ids of drafts created
    started_at: datetime = Field(default_factory=utcnow)

class CrewAssignment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("dsp"))
    user_id: str
    crew: str
    job_id: str
    job_name: str
    date: datetime
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    user_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    channel: Literal["chat", "sms"] = "chat"
    from_number: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

class SettingsUpdate(BaseModel):
    phone_number: Optional[str] = None
    sms_opt_in: Optional[bool] = None
    ghl_access_token: Optional[str] = None  # write-only
    ghl_location_id: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_from_number: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str

class ChatSendRequest(BaseModel):
    content: str
    photo_url: Optional[str] = None

# ---------------- Auth Helpers ----------------
async def get_current_user(request: Request) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.split(" ", 1)[1]
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    exp = session.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < utcnow():
        raise HTTPException(status_code=401, detail="Session expired")
    doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=401, detail="User not found")
    return User(**doc)

# ---------------- Auth ----------------
@api_router.post("/auth/session", response_model=SessionResponse)
async def create_session(payload: SessionRequest):
    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": payload.session_id},
        )
    if r.status_code != 200:
        raise HTTPException(401, "Invalid session_id")
    data = r.json()
    email = data.get("email"); name = data.get("name") or email
    picture = data.get("picture"); session_token = data.get("session_token")
    if not (email and session_token):
        raise HTTPException(401, "Missing auth data")
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {"name": name, "picture": picture}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name,
            "picture": picture, "created_at": utcnow(),
        })
        await seed_user_data(user_id)
    await db.user_sessions.insert_one({
        "session_token": session_token, "user_id": user_id,
        "created_at": utcnow(), "expires_at": utcnow() + timedelta(days=7),
    })
    doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return SessionResponse(session_token=session_token, user=User(**doc))

@api_router.post("/auth/dev-login", response_model=SessionResponse)
async def dev_login():
    email = "demo@subsidekick.com"
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": "Mike (Office)",
            "picture": None, "created_at": utcnow(),
        })
        await seed_user_data(user_id)
    session_token = f"dev_{uuid.uuid4().hex}"
    await db.user_sessions.insert_one({
        "session_token": session_token, "user_id": user_id,
        "created_at": utcnow(), "expires_at": utcnow() + timedelta(days=7),
    })
    doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return SessionResponse(session_token=session_token, user=User(**doc))

@api_router.get("/auth/me", response_model=User)
async def auth_me(user: User = Depends(get_current_user)):
    return user

@api_router.post("/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}

# ---------------- Seed ----------------
async def seed_user_data(user_id: str):
    jobs = [
        Job(user_id=user_id, code="RIV", name="Riverstone Apartments", gc="Ellis Construction",
            address="Fort Mill, SC", crew="Martinez Crew", crew_size=7, progress=55, status="active",
            working_on="Building C — Footings", next_milestone="Pour at 9:30 AM"),
        Job(user_id=user_id, code="OAK", name="Oak & Main Retail", gc="Turner-Hall Builders",
            address="Charlotte, NC", crew="Davis Crew", crew_size=5, progress=35, status="active",
            working_on="South wall — CMU", next_milestone="Block delivery 7:00 AM"),
        Job(user_id=user_id, code="HIL", name="Hillcrest Residence", gc="Waxhaw Homes",
            address="Waxhaw, NC", crew="Wilson Crew", crew_size=4, progress=70, status="active",
            working_on="Level 2 — Framing", next_milestone="Inspection 2:00 PM"),
    ]
    for j in jobs:
        await db.jobs.insert_one(j.model_dump())

    team = [
        TeamMember(user_id=user_id, name="Rick Martinez", role="Superintendent",
            phone_number="+19045550101", timezone="America/New_York", briefing_hour=6, briefing_minute=30),
        TeamMember(user_id=user_id, name="Sam Davis", role="Superintendent",
            phone_number="+19045550102", timezone="America/New_York", briefing_hour=6, briefing_minute=30),
        TeamMember(user_id=user_id, name="Tom Wilson", role="Superintendent",
            phone_number="+19045550103", timezone="America/New_York", briefing_hour=6, briefing_minute=30),
    ]
    for t in team:
        await db.team_members.insert_one(t.model_dump())

    old = utcnow() - timedelta(days=10)
    co1 = ChangeOrder(user_id=user_id, job_id=jobs[0].id, job_name=jobs[0].name,
        title="Added thickened slab edge at loading dock",
        description="Rob had us add another 86 feet of thickened edge. Took 3 guys most of the afternoon and about two yards extra.",
        ai_estimate=3850.0, labor_hours=12, material_notes="2 yd concrete",
        amount=3850.0, status="draft", reported_by="Rick Martinez", reported_by_phone="+19045550101",
        source="call")
    d = co1.model_dump(); d["created_at"] = old
    await db.change_orders.insert_one(d)

    bc1 = BackCharge(user_id=user_id, job_id=jobs[1].id, job_name=jobs[1].name,
        title="Cleanup charge disputed — debris was another trade",
        description="Turner-Hall trying to back-charge us $800 for jobsite cleanup this morning. Debris was framer's scraps, not ours. I've got 3 photos with timestamps.",
        amount=800.0, status="disputed", reported_by="Sam Davis", reported_by_phone="+19045550102",
        source="call")
    d = bc1.model_dump(); d["created_at"] = old
    await db.back_charges.insert_one(d)

    sc1 = ScheduleChange(user_id=user_id, job_id=jobs[2].id, job_name=jobs[2].name,
        description="GC pushed level 2 framing inspection from Tuesday 8am to Thursday 2pm — waiting on drywall inspector.",
        new_date=utcnow() + timedelta(days=2, hours=8),
        status="draft", reported_by="Tom Wilson", reported_by_phone="+19045550103", source="call")
    sc2 = ScheduleChange(user_id=user_id, job_id=jobs[1].id, job_name=jobs[1].name,
        description="Block delivery bumped 24 hrs — vendor issue. Waiting on GC confirmation.",
        status="draft", reported_by="Sam Davis", reported_by_phone="+19045550102", source="call")
    await db.schedule_changes.insert_many([sc1.model_dump(), sc2.model_dump()])

    ins1 = Inspection(user_id=user_id, job_id=jobs[2].id, job_name=jobs[2].name,
        inspection_type="Framing", result="pending", notes="Level 2 — Thursday 2pm.")
    await db.inspections.insert_one(ins1.model_dump())

    tomorrow = (utcnow() + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
    dispatches = [
        CrewAssignment(user_id=user_id, crew="Martinez Crew", job_id=jobs[0].id, job_name=jobs[0].name,
                       date=tomorrow, notes="Continue Building C footings. Pour prep."),
        CrewAssignment(user_id=user_id, crew="Davis Crew", job_id=jobs[1].id, job_name=jobs[1].name,
                       date=tomorrow, notes="South wall CMU. Block delivery 7am."),
        CrewAssignment(user_id=user_id, crew="Wilson Crew", job_id=jobs[2].id, job_name=jobs[2].name,
                       date=tomorrow + timedelta(hours=1), notes="Level 2 framing continuation."),
    ]
    await db.crew_assignments.insert_many([d.model_dump() for d in dispatches])

    # Call logs
    now = utcnow()
    calls = [
        CallLog(user_id=user_id, direction="inbound", channel="voice",
            from_number="+19045550101", to_number="+12295857126",
            team_member_id=team[0].id, team_member_name=team[0].name,
            duration_sec=142, summary="Reported change order on Riverstone — slab edge.",
            extracted_drafts=[co1.id], started_at=now - timedelta(hours=20)),
        CallLog(user_id=user_id, direction="inbound", channel="voice",
            from_number="+19045550102", to_number="+12295857126",
            team_member_id=team[1].id, team_member_name=team[1].name,
            duration_sec=98, summary="Back charge dispute at Oak & Main.",
            extracted_drafts=[bc1.id], started_at=now - timedelta(hours=3)),
        CallLog(user_id=user_id, direction="outbound", channel="voice",
            from_number="+12295857126", to_number="+19045550103",
            team_member_id=team[2].id, team_member_name=team[2].name,
            duration_sec=64, summary="Morning briefing — Hillcrest, framing prep, inspection 2pm.",
            started_at=now.replace(hour=6, minute=30, second=0, microsecond=0)),
    ]
    for c in calls:
        await db.call_logs.insert_one(c.model_dump())

# ---------------- Jobs ----------------
@api_router.get("/jobs", response_model=List[Job])
async def list_jobs(user: User = Depends(get_current_user)):
    docs = await db.jobs.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Job(**d) for d in docs]

@api_router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, user: User = Depends(get_current_user)):
    doc = await db.jobs.find_one({"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not doc: raise HTTPException(404, "Job not found")
    return Job(**doc)

# ---------------- Change Orders ----------------
@api_router.get("/change-orders", response_model=List[ChangeOrder])
async def list_change_orders(user: User = Depends(get_current_user)):
    docs = await db.change_orders.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [ChangeOrder(**d) for d in docs]

@api_router.patch("/change-orders/{co_id}", response_model=ChangeOrder)
async def update_co(co_id: str, payload: StatusUpdate, user: User = Depends(get_current_user)):
    await db.change_orders.update_one(
        {"id": co_id, "user_id": user.user_id}, {"$set": {"status": payload.status}}
    )
    doc = await db.change_orders.find_one({"id": co_id, "user_id": user.user_id}, {"_id": 0})
    if not doc: raise HTTPException(404, "Not found")
    return ChangeOrder(**doc)

# ---------------- Back Charges ----------------
@api_router.get("/back-charges", response_model=List[BackCharge])
async def list_bc(user: User = Depends(get_current_user)):
    docs = await db.back_charges.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [BackCharge(**d) for d in docs]

@api_router.patch("/back-charges/{bc_id}", response_model=BackCharge)
async def update_bc(bc_id: str, payload: StatusUpdate, user: User = Depends(get_current_user)):
    await db.back_charges.update_one(
        {"id": bc_id, "user_id": user.user_id}, {"$set": {"status": payload.status}}
    )
    doc = await db.back_charges.find_one({"id": bc_id, "user_id": user.user_id}, {"_id": 0})
    if not doc: raise HTTPException(404, "Not found")
    return BackCharge(**doc)

# ---------------- Schedule Changes ----------------
@api_router.get("/schedule-changes", response_model=List[ScheduleChange])
async def list_sc(user: User = Depends(get_current_user)):
    docs = await db.schedule_changes.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [ScheduleChange(**d) for d in docs]

@api_router.patch("/schedule-changes/{sc_id}", response_model=ScheduleChange)
async def update_sc(sc_id: str, payload: StatusUpdate, user: User = Depends(get_current_user)):
    await db.schedule_changes.update_one(
        {"id": sc_id, "user_id": user.user_id}, {"$set": {"status": payload.status}}
    )
    doc = await db.schedule_changes.find_one({"id": sc_id, "user_id": user.user_id}, {"_id": 0})
    if not doc: raise HTTPException(404, "Not found")
    return ScheduleChange(**doc)

# ---------------- Inspections ----------------
@api_router.get("/inspections", response_model=List[Inspection])
async def list_ins(user: User = Depends(get_current_user)):
    docs = await db.inspections.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Inspection(**d) for d in docs]

# ---------------- Team ----------------
@api_router.get("/team", response_model=List[TeamMember])
async def list_team(user: User = Depends(get_current_user)):
    docs = await db.team_members.find({"user_id": user.user_id, "active": True}, {"_id": 0}).sort("created_at", 1).to_list(50)
    return [TeamMember(**d) for d in docs]

@api_router.post("/team", response_model=TeamMember)
async def create_team_member(payload: TeamMemberCreate, user: User = Depends(get_current_user)):
    pn = "".join(ch for ch in payload.phone_number if ch.isdigit() or ch == "+").strip()
    if pn and not pn.startswith("+"):
        pn = "+" + pn
    if len(pn) < 8:
        raise HTTPException(400, "Invalid phone number")
    tm = TeamMember(user_id=user.user_id, **{**payload.model_dump(), "phone_number": pn})
    await db.team_members.insert_one(tm.model_dump())
    return tm

@api_router.patch("/team/{tm_id}", response_model=TeamMember)
async def update_team_member(tm_id: str, payload: TeamMemberUpdate, user: User = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "phone_number" in updates:
        pn = "".join(ch for ch in updates["phone_number"] if ch.isdigit() or ch == "+").strip()
        if pn and not pn.startswith("+"): pn = "+" + pn
        if len(pn) < 8: raise HTTPException(400, "Invalid phone number")
        updates["phone_number"] = pn
    if not updates:
        raise HTTPException(400, "No updates provided")
    r = await db.team_members.update_one({"id": tm_id, "user_id": user.user_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(404, "Team member not found")
    doc = await db.team_members.find_one({"id": tm_id, "user_id": user.user_id}, {"_id": 0})
    return TeamMember(**doc)

@api_router.delete("/team/{tm_id}")
async def delete_team_member(tm_id: str, user: User = Depends(get_current_user)):
    r = await db.team_members.update_one({"id": tm_id, "user_id": user.user_id}, {"$set": {"active": False}})
    if r.matched_count == 0: raise HTTPException(404, "Team member not found")
    return {"ok": True}

# ---------------- Call Logs ----------------
@api_router.get("/calls", response_model=List[CallLog])
async def list_calls(user: User = Depends(get_current_user)):
    docs = await db.call_logs.find({"user_id": user.user_id}, {"_id": 0}).sort("started_at", -1).to_list(100)
    return [CallLog(**d) for d in docs]

# ---------------- Briefing for a specific super (used by GHL/Twilio) ----------------
async def _build_super_briefing(user_id: str, team_member_id: Optional[str]) -> str:
    jobs_for = []
    if team_member_id:
        tm = await db.team_members.find_one({"id": team_member_id, "user_id": user_id}, {"_id": 0})
        crew_name = tm["name"].split(" ")[-1] + " Crew" if tm else None
    else:
        tm = None
        crew_name = None
    jobs = await db.jobs.find({"user_id": user_id, "status": "active"}, {"_id": 0}).to_list(20)
    if crew_name:
        jobs_for = [j for j in jobs if crew_name.lower() in (j.get("crew") or "").lower()] or jobs[:1]
    else:
        jobs_for = jobs
    # Open drafts
    cos = await db.change_orders.find({"user_id": user_id, "status": {"$in": ["draft", "pending"]}}, {"_id": 0}).to_list(20)
    bcs = await db.back_charges.find({"user_id": user_id, "status": {"$in": ["draft", "disputed"]}}, {"_id": 0}).to_list(20)
    scs = await db.schedule_changes.find({"user_id": user_id, "status": {"$in": ["draft", "notified"]}}, {"_id": 0}).to_list(20)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        ctx = f"Super name: {tm['name'] if tm else 'Foreman'}\n"
        ctx += "Today's jobs:\n"
        for j in jobs_for:
            ctx += f"- {j['name']} in {j['address']}: {j.get('working_on') or ''}. Next: {j.get('next_milestone') or ''}\n"
        if cos: ctx += "\nOpen change orders needing office decision:\n" + "\n".join(f"- {c['title'] or c['description']}" for c in cos)
        if bcs: ctx += "\nOpen back charge disputes:\n" + "\n".join(f"- {b['title'] or b['description']}" for b in bcs)
        if scs: ctx += "\nSchedule changes waiting:\n" + "\n".join(f"- {s['description']}" for s in scs)

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"briefing_{user_id}_{team_member_id or 'all'}",
            system_message=(
                "You are SubSidekick, an AI foreman on the phone. Give a short (4-6 sentences), "
                "spoken-word morning briefing to the superintendent. Start with 'Morning, <first name>.' "
                "Speak plainly, like a seasoned foreman. No bullets. Mention their job(s), what's on tap, "
                "and any office decisions the field is waiting on. End with 'What do you need me to do?'."
            ),
        ).with_model("openai", "gpt-5.4-mini")
        r = await chat.send_message(UserMessage(text=ctx))
        return r if isinstance(r, str) else str(r)
    except Exception:
        first = (tm["name"].split(" ")[0] if tm else "boss")
        return f"Morning, {first}. You've got {len(jobs_for)} jobs on the board. Let's go."

@api_router.get("/briefing")
async def briefing(user: User = Depends(get_current_user)):
    """Office-view briefing preview (all crews)."""
    summary = await _build_super_briefing(user.user_id, None)
    jobs = await db.jobs.count_documents({"user_id": user.user_id, "status": "active"})
    cos = await db.change_orders.count_documents({"user_id": user.user_id, "status": {"$in": ["draft", "pending"]}})
    bcs = await db.back_charges.count_documents({"user_id": user.user_id, "status": {"$in": ["draft", "disputed"]}})
    scs = await db.schedule_changes.count_documents({"user_id": user.user_id, "status": {"$in": ["draft", "notified"]}})
    return {
        "summary": summary,
        "active_jobs": jobs,
        "drafts_pending": cos,
        "back_charges_open": bcs,
        "schedule_changes_open": scs,
        "action_items_count": cos + bcs + scs,
        "date": utcnow().isoformat(),
    }

@api_router.get("/team/{tm_id}/briefing")
async def team_briefing(tm_id: str, user: User = Depends(get_current_user)):
    """Returns spoken briefing for a specific super (GHL fetches this before dialing)."""
    tm = await db.team_members.find_one({"id": tm_id, "user_id": user.user_id}, {"_id": 0})
    if not tm: raise HTTPException(404, "Team member not found")
    text = await _build_super_briefing(user.user_id, tm_id)
    return {"team_member_id": tm_id, "name": tm["name"], "phone": tm["phone_number"], "briefing": text}

@api_router.post("/team/{tm_id}/trigger-briefing")
async def trigger_briefing(tm_id: str, user: User = Depends(get_current_user)):
    """Sends the briefing as an SMS (fallback when GHL isn't wired yet)."""
    tm = await db.team_members.find_one({"id": tm_id, "user_id": user.user_id}, {"_id": 0})
    if not tm: raise HTTPException(404, "Team member not found")
    text = await _build_super_briefing(user.user_id, tm_id)
    body = f"[SubSidekick Morning Briefing]\n{text}"
    result = await run_in_threadpool(_send_sms_sync, tm["phone_number"], body)
    call = CallLog(
        user_id=user.user_id, direction="outbound", channel="sms",
        from_number=TWILIO_FROM or "office", to_number=tm["phone_number"],
        team_member_id=tm_id, team_member_name=tm["name"],
        summary=f"Morning briefing SMS ({result.get('provider')})", transcript=text,
    )
    await db.call_logs.insert_one(call.model_dump())
    return {"delivered_via": result.get("provider"), "twilio_configured": bool(_twilio_client()), "call_id": call.id, "body": body}

# ---------------- Digest (Office view) ----------------
@api_router.get("/digest")
async def digest(user: User = Depends(get_current_user)):
    cos = await db.change_orders.find({"user_id": user.user_id, "status": {"$in": ["draft", "pending"]}}, {"_id": 0}).sort("created_at", -1).to_list(50)
    bcs = await db.back_charges.find({"user_id": user.user_id, "status": {"$in": ["draft", "disputed"]}}, {"_id": 0}).sort("created_at", -1).to_list(50)
    scs = await db.schedule_changes.find({"user_id": user.user_id, "status": {"$in": ["draft", "notified"]}}, {"_id": 0}).sort("created_at", -1).to_list(50)
    inspections = await db.inspections.find({"user_id": user.user_id, "result": "fail"}, {"_id": 0}).to_list(50)
    jobs = await db.jobs.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).sort("created_at", 1).to_list(50)
    money_at_risk = sum((c.get("amount") or 0) for c in cos) + sum((b.get("amount") or 0) for b in bcs)
    return {
        "change_orders": [ChangeOrder(**d).model_dump(mode="json") for d in cos],
        "back_charges": [BackCharge(**d).model_dump(mode="json") for d in bcs],
        "schedule_changes": [ScheduleChange(**d).model_dump(mode="json") for d in scs],
        "failed_inspections": [Inspection(**d).model_dump(mode="json") for d in inspections],
        "jobs": [Job(**d).model_dump(mode="json") for d in jobs],
        "action_required_count": len(cos) + len(bcs) + len(scs) + len(inspections),
        "money_at_risk": money_at_risk,
    }

# ---------------- Missed money ----------------
@api_router.get("/missed-money")
async def missed_money(user: User = Depends(get_current_user)):
    cutoff = utcnow() - timedelta(days=7)
    cos = await db.change_orders.find(
        {"user_id": user.user_id, "status": {"$in": ["draft", "pending"]}, "created_at": {"$lte": cutoff}}, {"_id": 0}
    ).to_list(200)
    bcs = await db.back_charges.find(
        {"user_id": user.user_id, "status": {"$in": ["draft", "disputed"]}, "created_at": {"$lte": cutoff}}, {"_id": 0}
    ).to_list(200)
    co_total = sum((c.get("amount") or 0) for c in cos)
    bc_total = sum((b.get("amount") or 0) for b in bcs)
    return {
        "unsigned_change_orders_total": co_total,
        "disputed_back_charges_total": bc_total,
        "grand_total": co_total + bc_total,
        "unsigned_change_orders_count": len(cos),
        "disputed_back_charges_count": len(bcs),
        "cutoff_days": 7,
    }

# ---------------- Dispatch ----------------
@api_router.get("/dispatch")
async def get_dispatch(user: User = Depends(get_current_user)):
    now = utcnow()
    start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = await db.crew_assignments.find(
        {"user_id": user.user_id, "date": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).to_list(200)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["crew"], []).append(CrewAssignment(**r).model_dump(mode="json"))
    ordered = [{"crew": c, "assignments": sorted(items, key=lambda x: x["date"])} for c, items in sorted(groups.items())]
    return {"date": start.isoformat(), "crews": ordered, "total": len(rows)}

class DispatchUpdate(BaseModel):
    crew: Optional[str] = None
    job_id: Optional[str] = None
    date: Optional[datetime] = None
    notes: Optional[str] = None

@api_router.patch("/dispatch/{dispatch_id}", response_model=CrewAssignment)
async def update_dispatch(dispatch_id: str, payload: DispatchUpdate, user: User = Depends(get_current_user)):
    updates: dict = {}
    if payload.job_id is not None:
        job = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
        if not job: raise HTTPException(404, "Job not found")
        updates["job_id"] = payload.job_id
        updates["job_name"] = job["name"]
    if payload.crew is not None: updates["crew"] = payload.crew
    if payload.date is not None: updates["date"] = payload.date
    if payload.notes is not None: updates["notes"] = payload.notes
    if not updates: raise HTTPException(400, "No updates provided")
    r = await db.crew_assignments.update_one({"id": dispatch_id, "user_id": user.user_id}, {"$set": updates})
    if r.matched_count == 0: raise HTTPException(404, "Assignment not found")
    doc = await db.crew_assignments.find_one({"id": dispatch_id, "user_id": user.user_id}, {"_id": 0})
    return CrewAssignment(**doc)

# ---------------- Chat / SMS Fallback ----------------
@api_router.get("/chat/history", response_model=List[ChatMessage])
async def chat_history(channel: Optional[str] = None, user: User = Depends(get_current_user)):
    q: dict = {"user_id": user.user_id}
    if channel: q["channel"] = channel
    docs = await db.chat_messages.find(q, {"_id": 0}).sort("created_at", 1).to_list(200)
    return [ChatMessage(**d) for d in docs]

async def _chat_with_context(user_id: str, content: str, channel: str = "chat", from_number: Optional[str] = None) -> dict:
    # store user msg
    u_msg = ChatMessage(user_id=user_id, role="user", content=content, channel=channel, from_number=from_number)
    await db.chat_messages.insert_one(u_msg.model_dump())
    # Get history (SMS keeps memory across messages)
    history = await db.chat_messages.find(
        {"user_id": user_id, "channel": channel} if channel == "sms" else {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(50)
    jobs = await db.jobs.find({"user_id": user_id, "status": "active"}, {"_id": 0}).to_list(20)
    job_ctx = "Active jobs: " + "; ".join(f"{j['name']} (GC: {j['gc']}, {j['crew']})" for j in jobs)

    ai_text = "Got it. I've noted it down. Office will follow up."
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"chat_{user_id}_{channel}",
            system_message=(
                "You are SubSidekick, an AI foreman for a small subcontractor. Blue-collar, rugged, short sentences. "
                "When the caller mentions extra work, back charges, failed inspections, or schedule changes, "
                "confirm you're logging it as a DRAFT for the office. Never confirm final approval — the office decides. "
                "Keep replies under 3 short sentences. "
                f"Context: {job_ctx}"
            ),
        ).with_model("openai", "gpt-5.4-mini")
        r = await chat.send_message(UserMessage(text=content))
        ai_text = r if isinstance(r, str) else str(r)
    except Exception:
        logger.exception("chat llm failed")

    a_msg = ChatMessage(user_id=user_id, role="assistant", content=ai_text, channel=channel)
    await db.chat_messages.insert_one(a_msg.model_dump())

    # Draft detection (rules identical to previous impl)
    action_hint = None; route_hint = None
    tl = content.lower()
    if any(k in tl for k in ["wrap it up", "wrap up the day", "end of day", "call it a day", "day is done"]):
        route_hint = "/checkin"; action_hint = "start_checkin"
    if any(k in tl for k in ["change order", "extra work", "not in the bid", "added scope"]):
        if jobs:
            j = jobs[0]
            co = ChangeOrder(
                user_id=user_id, job_id=j["id"], job_name=j["name"],
                description=content, status="draft", reported_by=from_number or "SMS",
                source=("sms" if channel == "sms" else "chat"),
            )
            await db.change_orders.insert_one(co.model_dump())
            action_hint = "change_order_draft_created"
    elif "back charge" in tl or "back-charge" in tl:
        if jobs:
            j = jobs[0]
            bc = BackCharge(
                user_id=user_id, job_id=j["id"], job_name=j["name"],
                description=content, amount=0.0, status="disputed",
                source=("sms" if channel == "sms" else "chat"),
            )
            await db.back_charges.insert_one(bc.model_dump())
            action_hint = "back_charge_draft_created"
    elif any(k in tl for k in ["schedule change", "reschedule", "pushed to", "moved to", "delayed"]):
        if jobs:
            j = jobs[0]
            sc = ScheduleChange(
                user_id=user_id, job_id=j["id"], job_name=j["name"],
                description=content, status="draft", reported_by=from_number or "SMS",
                source=("sms" if channel == "sms" else "chat"),
            )
            await db.schedule_changes.insert_one(sc.model_dump())
            action_hint = "schedule_change_draft_created"

    return {"user_message": u_msg.model_dump(mode="json"),
            "ai_message": a_msg.model_dump(mode="json"),
            "action_hint": action_hint, "route_hint": route_hint}

@api_router.post("/chat/send")
async def chat_send(payload: ChatSendRequest, user: User = Depends(get_current_user)):
    return await _chat_with_context(user.user_id, payload.content, channel="chat")

# ---------------- Twilio SMS Webhook (inbound) ----------------
@api_router.post("/webhooks/twilio/sms")
async def twilio_sms_inbound(request: Request):
    """Twilio POSTs form-encoded. From=+E164, Body=text, To=twilio number."""
    form = await request.form()
    from_number = (form.get("From") or "").strip()
    body = (form.get("Body") or "").strip()
    to_number = (form.get("To") or "").strip()
    # Route to the team member's owner
    tm = await db.team_members.find_one({"phone_number": from_number, "active": True}, {"_id": 0})
    if not tm:
        # Unknown sender — return a friendly TwiML
        twiml = "<?xml version='1.0' encoding='UTF-8'?><Response><Message>This number isn't set up yet. Ask your office admin to add you to SubSidekick.</Message></Response>"
        return Response(content=twiml, media_type="application/xml")
    result = await _chat_with_context(tm["user_id"], body, channel="sms", from_number=from_number)
    # Log the exchange as a CallLog (sms channel)
    call = CallLog(
        user_id=tm["user_id"], direction="inbound", channel="sms",
        from_number=from_number, to_number=to_number,
        team_member_id=tm["id"], team_member_name=tm["name"],
        transcript=body, summary=(result["ai_message"]["content"][:200]),
    )
    await db.call_logs.insert_one(call.model_dump())
    twiml = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{result['ai_message']['content']}</Message></Response>"
    return Response(content=twiml, media_type="application/xml")

# ---------------- GHL Webhook (Voice AI) ----------------
@api_router.post("/webhooks/ghl/voice-ai")
async def ghl_voice_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-ghl-signature") or request.headers.get("X-GHL-Signature")
    verified = _verify_ghl_signature(raw, sig) if _ghl_pubkey else False
    try:
        payload = json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    # Identify user via mapped phone (to_number = office's Twilio) — use first user for demo
    data = payload.get("data") or payload
    call_id = str(data.get("callId") or data.get("call_id") or new_id("ghlcall"))
    already = await db.ghl_events.find_one({"event_id": call_id}, {"_id": 0})
    if already:
        return {"ok": True, "duplicate": True}
    from_number = data.get("from") or data.get("fromNumber") or ""
    to_number = data.get("to") or data.get("toNumber") or ""
    tm = await db.team_members.find_one({"phone_number": from_number, "active": True}, {"_id": 0})
    if not tm:
        # Fallback to first user
        first_user = await db.users.find_one({}, {"_id": 0}, sort=[("created_at", 1)])
        if not first_user:
            return {"ok": True, "skipped": "no user"}
        user_id = first_user["user_id"]; tm_id = None; tm_name = None
    else:
        user_id = tm["user_id"]; tm_id = tm["id"]; tm_name = tm["name"]
    transcript = data.get("transcript") or data.get("fullTranscript") or ""
    summary = data.get("summary") or transcript[:200]
    duration = int(data.get("duration") or 0)
    extracted = data.get("extracted") or data.get("structuredData") or {
        "change_orders": data.get("changeOrders", []),
        "back_charges": data.get("backCharges", []),
        "schedule_changes": data.get("scheduleChanges", []),
    }
    created_ids: list[str] = []
    # Pick a target job for each draft (first job in extracted's job_name match, else first active)
    active_jobs = await db.jobs.find({"user_id": user_id, "status": "active"}, {"_id": 0}).to_list(20)
    def match_job(name_hint: Optional[str]):
        if name_hint:
            for j in active_jobs:
                if name_hint.lower() in j["name"].lower(): return j
        return active_jobs[0] if active_jobs else None
    for co in (extracted.get("change_orders") or []):
        j = match_job(co.get("job") or co.get("job_name"))
        if not j: continue
        draft = ChangeOrder(user_id=user_id, job_id=j["id"], job_name=j["name"],
            title=(co.get("title") or "")[:120], description=co.get("description") or transcript[:400],
            amount=co.get("amount"), ai_estimate=co.get("estimate") or co.get("amount"),
            labor_hours=co.get("labor_hours"), material_notes=co.get("materials"),
            status="draft", reported_by=tm_name or "Voice AI", reported_by_phone=from_number,
            source="call", call_id=call_id)
        await db.change_orders.insert_one(draft.model_dump()); created_ids.append(draft.id)
    for bc in (extracted.get("back_charges") or []):
        j = match_job(bc.get("job") or bc.get("job_name"))
        if not j: continue
        draft = BackCharge(user_id=user_id, job_id=j["id"], job_name=j["name"],
            title=(bc.get("title") or "")[:120], description=bc.get("description") or transcript[:400],
            amount=float(bc.get("amount") or 0), status="disputed",
            reported_by=tm_name or "Voice AI", reported_by_phone=from_number,
            source="call", call_id=call_id)
        await db.back_charges.insert_one(draft.model_dump()); created_ids.append(draft.id)
    for sc in (extracted.get("schedule_changes") or []):
        j = match_job(sc.get("job") or sc.get("job_name"))
        if not j: continue
        draft = ScheduleChange(user_id=user_id, job_id=j["id"], job_name=j["name"],
            description=sc.get("description") or transcript[:400], status="draft",
            reported_by=tm_name or "Voice AI", reported_by_phone=from_number,
            source="call", call_id=call_id)
        await db.schedule_changes.insert_one(draft.model_dump()); created_ids.append(draft.id)
    call = CallLog(user_id=user_id, direction="inbound", channel="voice",
        from_number=from_number, to_number=to_number,
        team_member_id=tm_id, team_member_name=tm_name,
        duration_sec=duration, transcript=transcript, summary=summary,
        ghl_call_id=call_id, extracted_drafts=created_ids)
    await db.call_logs.insert_one(call.model_dump())
    await db.ghl_events.insert_one({"event_id": call_id, "received_at": utcnow(), "verified": verified})
    return {"ok": True, "call_id": call.id, "drafts_created": created_ids, "signature_verified": verified}

# ---------------- Settings ----------------
@api_router.patch("/settings", response_model=User)
async def update_settings(payload: SettingsUpdate, user: User = Depends(get_current_user)):
    up: dict = {}
    if payload.phone_number is not None:
        pn = "".join(ch for ch in payload.phone_number if ch.isdigit() or ch == "+").strip()
        if pn and not pn.startswith("+"): pn = "+" + pn
        if pn and len(pn) < 8: raise HTTPException(400, "Phone number looks invalid")
        up["phone_number"] = pn or None
    if payload.sms_opt_in is not None: up["sms_opt_in"] = payload.sms_opt_in
    if payload.ghl_location_id is not None: up["ghl_location_id"] = payload.ghl_location_id.strip() or None
    if payload.ghl_access_token is not None:
        up["ghl_access_token_encrypted"] = payload.ghl_access_token  # dev-mode only; encrypt in prod
        up["ghl_access_token_set"] = bool(payload.ghl_access_token)
    if payload.twilio_from_number is not None:
        up["twilio_from_number"] = payload.twilio_from_number
        up["twilio_configured"] = bool(payload.twilio_from_number and payload.twilio_account_sid)
    if up:
        await db.users.update_one({"user_id": user.user_id}, {"$set": up})
    doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    return User(**doc)

# ---------------- Uploads ----------------
@api_router.post("/uploads/photo")
async def upload_photo(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    data = await file.read()
    if not data: raise HTTPException(400, "Empty")
    if len(data) > 15 * 1024 * 1024: raise HTTPException(413, "Too large")
    ext = (Path(file.filename or "photo.jpg").suffix or ".jpg").lstrip(".").lower()
    if ext not in {"jpg", "jpeg", "png", "webp", "heic"}: ext = "jpg"
    ct = file.content_type or f"image/{ext if ext != 'jpg' else 'jpeg'}"
    uid = uuid.uuid4().hex
    path = f"{APP_NAME}/uploads/{user.user_id}/{uid}.{ext}"
    try:
        result = await run_in_threadpool(_put_object_sync, path, data, ct)
    except Exception as e:
        logger.exception("upload failed"); raise HTTPException(502, str(e))
    await db.uploads.insert_one({
        "user_id": user.user_id, "storage_path": result.get("path", path),
        "content_type": ct, "size": result.get("size", len(data)), "created_at": utcnow(),
    })
    return {"storage_path": result.get("path", path), "url": f"/api/files/{result.get('path', path)}"}

@api_router.get("/files/{full_path:path}")
async def get_file(full_path: str, token: Optional[str] = Query(None), request: Request = None):
    auth = (request.headers.get("Authorization", "") if request else "")
    tok = token or (auth.split(" ", 1)[1] if auth.startswith("Bearer ") else None)
    if not tok: raise HTTPException(401, "Missing token")
    session = await db.user_sessions.find_one({"session_token": tok}, {"_id": 0})
    if not session: raise HTTPException(401, "Invalid session")
    upload = await db.uploads.find_one({"storage_path": full_path, "user_id": session["user_id"]}, {"_id": 0})
    if not upload: raise HTTPException(404, "Not found")
    try:
        content, ct = await run_in_threadpool(_get_object_sync, full_path)
    except Exception as e:
        raise HTTPException(502, str(e))
    return Response(content=content, media_type=ct, headers={"Cache-Control": "private, max-age=31536000"})

# ---------------- Recovery / Missed Money SMS ----------------
def _format_recovery_text(name: str, money: dict) -> str:
    return (
        f"SubSidekick weekly recap for {name.split(' ')[0]}: "
        f"${int(money['grand_total']):,} sitting on the table — "
        f"{money['unsigned_change_orders_count']} unsigned change orders "
        f"(${int(money['unsigned_change_orders_total']):,}) and "
        f"{money['disputed_back_charges_count']} disputed back charges "
        f"(${int(money['disputed_back_charges_total']):,}) over 7 days old. Open the app to knock 'em down."
    )

async def _compute_recovery(user_id: str) -> dict:
    cutoff = utcnow() - timedelta(days=7)
    cos = await db.change_orders.find(
        {"user_id": user_id, "status": {"$in": ["draft", "pending"]}, "created_at": {"$lte": cutoff}}, {"_id": 0}
    ).to_list(200)
    bcs = await db.back_charges.find(
        {"user_id": user_id, "status": {"$in": ["draft", "disputed"]}, "created_at": {"$lte": cutoff}}, {"_id": 0}
    ).to_list(200)
    co_t = sum((c.get("amount") or 0) for c in cos); bc_t = sum((b.get("amount") or 0) for b in bcs)
    return {"unsigned_change_orders_total": co_t, "disputed_back_charges_total": bc_t,
            "grand_total": co_t + bc_t, "unsigned_change_orders_count": len(cos),
            "disputed_back_charges_count": len(bcs)}

@api_router.get("/recovery/preview")
async def recovery_preview(user: User = Depends(get_current_user)):
    m = await _compute_recovery(user.user_id)
    return {"body": _format_recovery_text(user.name, m), "phone_number": user.phone_number, "sms_opt_in": user.sms_opt_in, "money": m}

@api_router.post("/recovery/send")
async def recovery_send(user: User = Depends(get_current_user)):
    if not user.phone_number: raise HTTPException(400, "No phone number on file.")
    m = await _compute_recovery(user.user_id)
    body = _format_recovery_text(user.name, m)
    result = await run_in_threadpool(_send_sms_sync, user.phone_number, body)
    await db.sms_outbox.insert_one({
        "user_id": user.user_id, "to": user.phone_number, "body": body,
        "provider": result.get("provider"), "sid": result.get("sid"), "error": result.get("error"),
        "created_at": utcnow(), "trigger": "manual",
    })
    return {"delivered_via": result.get("provider"), "body": body, "phone": user.phone_number,
            "sid": result.get("sid"), "twilio_configured": bool(_twilio_client())}

async def _run_weekly_recovery_for_all():
    async for u in db.users.find({"sms_opt_in": True, "phone_number": {"$ne": None}}, {"_id": 0}):
        try:
            m = await _compute_recovery(u["user_id"])
            if m["grand_total"] <= 0: continue
            body = _format_recovery_text(u.get("name") or "Foreman", m)
            r = await run_in_threadpool(_send_sms_sync, u["phone_number"], body)
            await db.sms_outbox.insert_one({
                "user_id": u["user_id"], "to": u["phone_number"], "body": body,
                "provider": r.get("provider"), "sid": r.get("sid"), "error": r.get("error"),
                "created_at": utcnow(), "trigger": "weekly",
            })
        except Exception: logger.exception("weekly recovery failed")

# ---------------- End of Day Checkin ----------------
class CheckinAnswerRequest(BaseModel):
    checkin_id: str
    job_id: str
    completed: str = ""
    issues: str = ""

class CheckinSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chk"))
    user_id: str
    job_ids: List[str]
    answered: List[str] = []
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

@api_router.post("/checkin/start")
async def checkin_start(user: User = Depends(get_current_user)):
    jobs = await db.jobs.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(50)
    if not jobs: raise HTTPException(400, "No active jobs")
    s = CheckinSession(user_id=user.user_id, job_ids=[j["id"] for j in jobs])
    await db.checkin_sessions.insert_one(s.model_dump())
    return {"checkin_id": s.id, "total_jobs": len(jobs), "current_index": 0, "current_job": jobs[0]}

@api_router.post("/checkin/answer")
async def checkin_answer(payload: CheckinAnswerRequest, user: User = Depends(get_current_user)):
    s = await db.checkin_sessions.find_one({"id": payload.checkin_id, "user_id": user.user_id}, {"_id": 0})
    if not s: raise HTTPException(404, "Checkin not found")
    j = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
    jn = j["name"] if j else payload.job_id
    log = f"[End-of-Day · {jn}] Completed: {payload.completed or '—'}. Issues: {payload.issues or 'none'}"
    await db.chat_messages.insert_one(ChatMessage(user_id=user.user_id, role="user", content=log).model_dump())
    if payload.issues and any(k in payload.issues.lower() for k in ["fail", "inspection"]):
        if j:
            ins = Inspection(user_id=user.user_id, job_id=payload.job_id, job_name=j["name"],
                inspection_type="Daily Check", result="fail", notes=payload.issues)
            await db.inspections.insert_one(ins.model_dump())
    answered = list(s.get("answered", []))
    if payload.job_id not in answered: answered.append(payload.job_id)
    remaining = [x for x in s["job_ids"] if x not in answered]
    upd = {"answered": answered}
    result = {"checkin_id": payload.checkin_id, "answered_count": len(answered), "total_jobs": len(s["job_ids"])}
    if remaining:
        nj = await db.jobs.find_one({"id": remaining[0], "user_id": user.user_id}, {"_id": 0})
        result["current_job"] = nj; result["done"] = False
    else:
        summary = "Day wrapped up. Nice work."
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            all_msgs = await db.chat_messages.find(
                {"user_id": user.user_id, "role": "user", "content": {"$regex": "^\\[End-of-Day"}}, {"_id": 0}
            ).sort("created_at", -1).to_list(len(s["job_ids"]))
            ctx = "\n".join(reversed([m["content"] for m in all_msgs[:len(s["job_ids"])]]))
            chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"eod_{user.user_id}_{payload.checkin_id}",
                system_message="You are SubSidekick. Given a foreman's end-of-day report per job, write a short 3-4 sentence summary for the office. Plain-spoken, no bullets. Highlight anything that failed or needs follow-up.",
            ).with_model("openai", "gpt-5.4-mini")
            r = await chat.send_message(UserMessage(text=ctx))
            summary = r if isinstance(r, str) else str(r)
        except Exception: pass
        upd["completed_at"] = utcnow(); upd["summary"] = summary
        result["done"] = True; result["summary"] = summary
    await db.checkin_sessions.update_one({"id": payload.checkin_id}, {"$set": upd})
    return result

# ---------------- Root ----------------
@api_router.get("/")
async def root():
    return {"service": "subsidekick", "status": "ok", "twilio_from": TWILIO_FROM or None,
            "twilio_configured": bool(_twilio_client()), "ghl_configured": bool(GHL_ACCESS_TOKEN)}

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

_scheduler = None
@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id", unique=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
        await db.ghl_events.create_index("event_id", unique=True)
    except Exception as e: logger.warning(f"index create: {e}")
    try:
        await run_in_threadpool(_init_storage_sync); logger.info("Object storage initialized")
    except Exception as e: logger.warning(f"object storage: {e}")
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        global _scheduler
        _scheduler = AsyncIOScheduler(timezone=timezone.utc)
        _scheduler.add_job(_run_weekly_recovery_for_all, CronTrigger(day_of_week="mon", hour=8, minute=0), id="weekly_recovery")
        _scheduler.start(); logger.info("Weekly recovery scheduler started")
    except Exception as e: logger.warning(f"scheduler: {e}")

@app.on_event("shutdown")
async def shutdown():
    client.close()
