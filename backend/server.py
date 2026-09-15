from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Request, Response, Query
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import logging
import tempfile
import inspect
import hashlib
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timedelta, timezone
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# ---------------- Emergent Object Storage ----------------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "subsidekick"
_storage_key: Optional[str] = None

def _init_storage_sync() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key

def _put_object_sync(path: str, data: bytes, content_type: str) -> dict:
    key = _init_storage_sync()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    if resp.status_code == 503:
        # stale key
        global _storage_key
        _storage_key = None
        key = _init_storage_sync()
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    resp.raise_for_status()
    return resp.json()

def _get_object_sync(path: str) -> tuple[bytes, str]:
    key = _init_storage_sync()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---------------- Models ----------------
def new_id(prefix: str = "id"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def utcnow():
    return datetime.now(timezone.utc)

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

class SessionRequest(BaseModel):
    session_id: str

class SessionResponse(BaseModel):
    session_token: str
    user: User

# --- Jobs ---
class Job(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job"))
    user_id: str
    name: str
    gc: str  # General Contractor
    address: str
    status: Literal["active", "on_hold", "completed"] = "active"
    crew: str = ""
    progress: int = 0  # 0-100
    created_at: datetime = Field(default_factory=utcnow)

class JobCreate(BaseModel):
    name: str
    gc: str
    address: str
    crew: str = ""
    status: Literal["active", "on_hold", "completed"] = "active"

# --- Change Orders ---
class ChangeOrder(BaseModel):
    id: str = Field(default_factory=lambda: new_id("co"))
    user_id: str
    job_id: str
    job_name: str
    description: str
    amount: Optional[float] = None
    status: Literal["draft", "pending", "approved", "rejected"] = "draft"
    reported_by: str = "Field"
    photo_url: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

class ChangeOrderCreate(BaseModel):
    job_id: str
    description: str
    amount: Optional[float] = None
    status: Literal["draft", "pending", "approved", "rejected"] = "draft"

# --- Back Charges ---
class BackCharge(BaseModel):
    id: str = Field(default_factory=lambda: new_id("bc"))
    user_id: str
    job_id: str
    job_name: str
    description: str
    amount: float
    status: Literal["draft", "disputed", "resolved"] = "draft"
    photo_url: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

class BackChargeCreate(BaseModel):
    job_id: str
    description: str
    amount: float
    photo_url: Optional[str] = None

# --- Inspections ---
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

class InspectionCreate(BaseModel):
    job_id: str
    inspection_type: str
    result: Literal["pass", "fail", "pending"] = "pending"
    notes: str = ""

# --- Chat / Messages ---
class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    user_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    audio_key: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

class ChatSendRequest(BaseModel):
    content: str
    photo_url: Optional[str] = None

# --- Crew Dispatch ---
class CrewAssignment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("dsp"))
    user_id: str
    crew: str
    job_id: str
    job_name: str
    date: datetime
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)

class CrewAssignmentCreate(BaseModel):
    crew: str
    job_id: str
    date: datetime
    notes: str = ""

# --- End of Day Checkin ---
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
    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    return User(**user_doc)

# ---------------- Auth Routes ----------------
@api_router.post("/auth/session", response_model=SessionResponse)
async def create_session(payload: SessionRequest):
    session_id = payload.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    async with httpx.AsyncClient(timeout=15) as http_client:
        r = await http_client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = r.json()
    email = data.get("email")
    name = data.get("name") or email
    picture = data.get("picture")
    session_token = data.get("session_token")
    if not (email and session_token):
        raise HTTPException(status_code=401, detail="Missing auth data")

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id}, {"$set": {"name": name, "picture": picture}}
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name,
            "picture": picture, "created_at": utcnow(),
        })
        await seed_user_data(user_id)

    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "created_at": utcnow(),
        "expires_at": utcnow() + timedelta(days=7),
    })
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return SessionResponse(session_token=session_token, user=User(**user_doc))

@api_router.post("/auth/dev-login", response_model=SessionResponse)
async def dev_login():
    """Creates a demo user session (for testing without Google OAuth)."""
    email = "demo@subsidekick.com"
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": "Dave (Demo Super)",
            "picture": None, "created_at": utcnow(),
        })
        await seed_user_data(user_id)
    session_token = f"dev_{uuid.uuid4().hex}"
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "created_at": utcnow(),
        "expires_at": utcnow() + timedelta(days=7),
    })
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return SessionResponse(session_token=session_token, user=User(**user_doc))

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

# ---------------- Seed data ----------------
async def seed_user_data(user_id: str):
    jobs = [
        Job(user_id=user_id, name="Riverside Apartments", gc="Acme Construction",
            address="1200 Riverside Dr", crew="Crew A", progress=65, status="active"),
        Job(user_id=user_id, name="Maple Street Renovation", gc="BuildRight LLC",
            address="45 Maple St", crew="Crew B", progress=40, status="active"),
        Job(user_id=user_id, name="Oak Ridge Commercial", gc="Titan GC",
            address="800 Oak Ridge Rd", crew="Crew A", progress=15, status="active"),
    ]
    for j in jobs:
        await db.jobs.insert_one(j.model_dump())
    # Change orders - one old for missed money radar
    old_created = utcnow() - timedelta(days=10)
    co1 = ChangeOrder(user_id=user_id, job_id=jobs[0].id, job_name=jobs[0].name,
        description="GC added extra work on east wall — extra concrete required.",
        amount=2800.0, status="draft", reported_by="Dave (Super)")
    co1_dict = co1.model_dump()
    co1_dict["created_at"] = old_created
    co2 = ChangeOrder(user_id=user_id, job_id=jobs[1].id, job_name=jobs[1].name,
        description="Additional framing for extended porch not in original bid.",
        amount=1450.0, status="pending", reported_by="Dave (Super)")
    co2_dict = co2.model_dump()
    co2_dict["created_at"] = old_created
    await db.change_orders.insert_many([co1_dict, co2_dict])
    # Back charges
    bc1 = BackCharge(user_id=user_id, job_id=jobs[0].id, job_name=jobs[0].name,
        description="GC claiming $800 back charge for cleanup — disputed, not our scope.",
        amount=800.0, status="disputed")
    bc1_dict = bc1.model_dump()
    bc1_dict["created_at"] = old_created
    await db.back_charges.insert_one(bc1_dict)
    # Inspections
    ins1 = Inspection(user_id=user_id, job_id=jobs[1].id, job_name=jobs[1].name,
        inspection_type="Framing", result="fail",
        notes="Failed framing inspection — need to reschedule and address issues on second floor.")
    ins2 = Inspection(user_id=user_id, job_id=jobs[0].id, job_name=jobs[0].name,
        inspection_type="Foundation", result="pass",
        notes="All good, ready to proceed.")
    await db.inspections.insert_many([ins1.model_dump(), ins2.model_dump()])
    # Dispatch for tomorrow
    tomorrow = (utcnow() + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
    dispatches = [
        CrewAssignment(user_id=user_id, crew="Crew A", job_id=jobs[0].id, job_name=jobs[0].name,
                       date=tomorrow, notes="Continue east wall pour. 7am start."),
        CrewAssignment(user_id=user_id, crew="Crew B", job_id=jobs[1].id, job_name=jobs[1].name,
                       date=tomorrow, notes="Rework framing before re-inspection."),
        CrewAssignment(user_id=user_id, crew="Crew A", job_id=jobs[2].id, job_name=jobs[2].name,
                       date=tomorrow + timedelta(hours=6), notes="Move over after Riverside pour cures."),
    ]
    await db.crew_assignments.insert_many([d.model_dump() for d in dispatches])

# ---------------- Jobs ----------------
@api_router.get("/jobs", response_model=List[Job])
async def list_jobs(user: User = Depends(get_current_user)):
    docs = await db.jobs.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Job(**d) for d in docs]

@api_router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, user: User = Depends(get_current_user)):
    doc = await db.jobs.find_one({"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Job not found")
    return Job(**doc)

@api_router.post("/jobs", response_model=Job)
async def create_job(payload: JobCreate, user: User = Depends(get_current_user)):
    job = Job(user_id=user.user_id, **payload.model_dump())
    await db.jobs.insert_one(job.model_dump())
    return job

# ---------------- Change Orders ----------------
@api_router.get("/change-orders", response_model=List[ChangeOrder])
async def list_change_orders(user: User = Depends(get_current_user)):
    docs = await db.change_orders.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [ChangeOrder(**d) for d in docs]

@api_router.post("/change-orders", response_model=ChangeOrder)
async def create_change_order(payload: ChangeOrderCreate, user: User = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    co = ChangeOrder(user_id=user.user_id, job_name=job["name"], **payload.model_dump())
    await db.change_orders.insert_one(co.model_dump())
    return co

class StatusUpdate(BaseModel):
    status: str

@api_router.patch("/change-orders/{co_id}", response_model=ChangeOrder)
async def update_change_order(co_id: str, payload: StatusUpdate, user: User = Depends(get_current_user)):
    await db.change_orders.update_one(
        {"id": co_id, "user_id": user.user_id}, {"$set": {"status": payload.status}}
    )
    doc = await db.change_orders.find_one({"id": co_id, "user_id": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    return ChangeOrder(**doc)

# ---------------- Back Charges ----------------
@api_router.get("/back-charges", response_model=List[BackCharge])
async def list_back_charges(user: User = Depends(get_current_user)):
    docs = await db.back_charges.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [BackCharge(**d) for d in docs]

@api_router.post("/back-charges", response_model=BackCharge)
async def create_back_charge(payload: BackChargeCreate, user: User = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    bc = BackCharge(user_id=user.user_id, job_name=job["name"], **payload.model_dump())
    await db.back_charges.insert_one(bc.model_dump())
    return bc

# ---------------- Inspections ----------------
@api_router.get("/inspections", response_model=List[Inspection])
async def list_inspections(user: User = Depends(get_current_user)):
    docs = await db.inspections.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Inspection(**d) for d in docs]

@api_router.post("/inspections", response_model=Inspection)
async def create_inspection(payload: InspectionCreate, user: User = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    ins = Inspection(user_id=user.user_id, job_name=job["name"], **payload.model_dump())
    await db.inspections.insert_one(ins.model_dump())
    return ins

# ---------------- Office Digest ----------------
@api_router.get("/digest")
async def office_digest(user: User = Depends(get_current_user)):
    action_cos = await db.change_orders.find(
        {"user_id": user.user_id, "status": {"$in": ["draft", "pending"]}}, {"_id": 0}
    ).to_list(50)
    disputed_bcs = await db.back_charges.find(
        {"user_id": user.user_id, "status": {"$in": ["draft", "disputed"]}}, {"_id": 0}
    ).to_list(50)
    failed_inspections = await db.inspections.find(
        {"user_id": user.user_id, "result": "fail"}, {"_id": 0}
    ).to_list(50)
    jobs = await db.jobs.find({"user_id": user.user_id}, {"_id": 0}).to_list(50)
    return {
        "change_orders": [ChangeOrder(**d).model_dump(mode="json") for d in action_cos],
        "back_charges": [BackCharge(**d).model_dump(mode="json") for d in disputed_bcs],
        "failed_inspections": [Inspection(**d).model_dump(mode="json") for d in failed_inspections],
        "jobs_count": len(jobs),
        "action_required_count": len(action_cos) + len(disputed_bcs) + len(failed_inspections),
    }

# ---------------- Morning Briefing ----------------
@api_router.get("/briefing")
async def morning_briefing(user: User = Depends(get_current_user)):
    jobs = await db.jobs.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(50)
    action_cos = await db.change_orders.find(
        {"user_id": user.user_id, "status": {"$in": ["draft", "pending"]}}, {"_id": 0}
    ).to_list(20)
    failed_ins = await db.inspections.find(
        {"user_id": user.user_id, "result": "fail"}, {"_id": 0}
    ).to_list(20)

    # Try LLM-powered summary; fallback if it fails
    summary_lines = []
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        prompt_ctx = "Today's jobs:\n"
        for j in jobs:
            prompt_ctx += f"- {j['name']} ({j['gc']}, {j['crew']}), progress {j['progress']}%\n"
        if action_cos:
            prompt_ctx += "\nOpen change orders:\n" + "\n".join(f"- {c['job_name']}: {c['description']}" for c in action_cos)
        if failed_ins:
            prompt_ctx += "\nFailed inspections:\n" + "\n".join(f"- {i['job_name']}: {i['notes']}" for i in failed_ins)

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"briefing_{user.user_id}",
            system_message=(
                "You are SubSidekick, the AI foreman for a small subcontractor. "
                "You are a rugged, blue-collar, no-nonsense assistant that speaks like a seasoned foreman. "
                "Give a short (5-7 sentences MAX), plain-spoken morning briefing. "
                "Start with 'Morning.' Keep it punchy, focus on what needs decision today. "
                "No corporate speak, no bullet points, just talk like a real foreman."
            ),
        ).with_model("openai", "gpt-5.4-mini")
        resp = await chat.send_message(UserMessage(text=prompt_ctx))
        summary = resp if isinstance(resp, str) else str(resp)
    except Exception as e:
        logger.exception("Briefing LLM failed")
        summary = (
            f"Morning. You've got {len(jobs)} active jobs on the board. "
            f"{len(action_cos)} change orders waiting for the office. "
            f"{len(failed_ins)} inspection issues to sort out. "
            "Let's get moving."
        )

    return {
        "summary": summary,
        "active_jobs": len(jobs),
        "action_items_count": len(action_cos) + len(failed_ins),
        "date": utcnow().isoformat(),
    }

# ---------------- Chat with AI Foreman ----------------
@api_router.get("/chat/history", response_model=List[ChatMessage])
async def chat_history(user: User = Depends(get_current_user)):
    docs = await db.chat_messages.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return [ChatMessage(**d) for d in docs]

@api_router.post("/chat/send")
async def chat_send(payload: ChatSendRequest, user: User = Depends(get_current_user)):
    user_msg = ChatMessage(user_id=user.user_id, role="user", content=payload.content)
    await db.chat_messages.insert_one(user_msg.model_dump())

    # Build context from prior messages
    history_docs = await db.chat_messages.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    # Provide job context
    jobs = await db.jobs.find({"user_id": user.user_id}, {"_id": 0}).to_list(50)
    job_ctx = "Active jobs: " + "; ".join(f"{j['name']} (GC: {j['gc']})" for j in jobs)

    ai_text = ""
    action_hint = None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"chat_{user.user_id}",
            system_message=(
                "You are SubSidekick, an AI foreman for a small subcontractor. "
                "You speak like a seasoned, rugged, blue-collar foreman: short sentences, plain words, no corporate fluff. "
                "You help capture: change orders (extra work from the GC), back charges (money the GC wants to take back), "
                "failed inspections, and end-of-day status. "
                "When the user mentions extra work, back charges, or inspection issues, acknowledge and confirm you'll log it as a DRAFT for the office to review. "
                "Keep replies under 3 short sentences. Never use bullet points. "
                f"Context — {job_ctx}"
            ),
        ).with_model("openai", "gpt-5.4-mini")

        # Just send the latest user message (session_id keeps context on Emergent side)
        resp = await chat.send_message(UserMessage(text=payload.content))
        ai_text = resp if isinstance(resp, str) else str(resp)
    except Exception as e:
        logger.exception("Chat LLM failed")
        ai_text = "Got it. I've noted it down. The office will follow up."

    ai_msg = ChatMessage(user_id=user.user_id, role="assistant", content=ai_text)
    await db.chat_messages.insert_one(ai_msg.model_dump())

    # Simple heuristic detection to auto-create drafts
    text_lower = payload.content.lower()
    if any(k in text_lower for k in ["change order", "extra work", "not in the bid", "added scope"]):
        # pick first active job as target if only one
        if jobs:
            j = jobs[0]
            co = ChangeOrder(
                user_id=user.user_id, job_id=j["id"], job_name=j["name"],
                description=payload.content, status="draft", reported_by=user.name,
            )
            co_dict = co.model_dump()
            if payload.photo_url:
                co_dict["photo_url"] = payload.photo_url
            await db.change_orders.insert_one(co_dict)
            action_hint = "change_order_draft_created"
    elif "back charge" in text_lower or "back-charge" in text_lower:
        if jobs:
            j = jobs[0]
            bc = BackCharge(
                user_id=user.user_id, job_id=j["id"], job_name=j["name"],
                description=payload.content, amount=0.0, status="disputed",
                photo_url=payload.photo_url,
            )
            await db.back_charges.insert_one(bc.model_dump())
            action_hint = "back_charge_draft_created"

    return {
        "user_message": user_msg.model_dump(mode="json"),
        "ai_message": ai_msg.model_dump(mode="json"),
        "action_hint": action_hint,
    }

# ---------------- Uploads (Emergent Object Storage) ----------------
@api_router.post("/uploads/photo")
async def upload_photo(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Photo too large")
    ext = (Path(file.filename or "photo.jpg").suffix or ".jpg").lstrip(".").lower()
    if ext not in {"jpg", "jpeg", "png", "webp", "heic"}:
        ext = "jpg"
    content_type = file.content_type or f"image/{ext if ext != 'jpg' else 'jpeg'}"
    obj_uuid = uuid.uuid4().hex
    storage_path = f"{APP_NAME}/uploads/{user.user_id}/{obj_uuid}.{ext}"
    try:
        result = await run_in_threadpool(_put_object_sync, storage_path, data, content_type)
    except Exception as e:
        logger.exception("Storage upload failed")
        raise HTTPException(502, f"Upload failed: {e}")
    await db.uploads.insert_one({
        "user_id": user.user_id,
        "storage_path": result.get("path", storage_path),
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "created_at": utcnow(),
    })
    return {
        "storage_path": result.get("path", storage_path),
        "url": f"/api/files/{result.get('path', storage_path)}",
    }

@api_router.get("/files/{full_path:path}")
async def get_file(full_path: str, token: Optional[str] = Query(None), request: Request = None):
    # Accept token from Authorization header OR query (for web <img>)
    auth = (request.headers.get("Authorization", "") if request else "")
    tok = token or (auth.split(" ", 1)[1] if auth.startswith("Bearer ") else None)
    if not tok:
        raise HTTPException(401, "Missing token")
    session = await db.user_sessions.find_one({"session_token": tok}, {"_id": 0})
    if not session:
        raise HTTPException(401, "Invalid session")
    # Ownership check via DB
    upload = await db.uploads.find_one({"storage_path": full_path, "user_id": session["user_id"]}, {"_id": 0})
    if not upload:
        raise HTTPException(404, "Not found")
    try:
        content, ct = await run_in_threadpool(_get_object_sync, full_path)
    except Exception as e:
        logger.exception("Storage download failed")
        raise HTTPException(502, f"Download failed: {e}")
    return Response(content=content, media_type=ct,
                    headers={"Cache-Control": "private, max-age=31536000"})

# ---------------- Missed Money Radar ----------------
@api_router.get("/missed-money")
async def missed_money(user: User = Depends(get_current_user)):
    cutoff = utcnow() - timedelta(days=7)
    open_cos_cursor = db.change_orders.find(
        {"user_id": user.user_id, "status": {"$in": ["draft", "pending"]}, "created_at": {"$lte": cutoff}},
        {"_id": 0},
    )
    open_cos = await open_cos_cursor.to_list(200)
    disputed_bcs_cursor = db.back_charges.find(
        {"user_id": user.user_id, "status": {"$in": ["draft", "disputed"]}, "created_at": {"$lte": cutoff}},
        {"_id": 0},
    )
    disputed_bcs = await disputed_bcs_cursor.to_list(200)
    co_total = sum((c.get("amount") or 0) for c in open_cos)
    bc_total = sum((b.get("amount") or 0) for b in disputed_bcs)
    return {
        "unsigned_change_orders_total": co_total,
        "disputed_back_charges_total": bc_total,
        "grand_total": co_total + bc_total,
        "unsigned_change_orders_count": len(open_cos),
        "disputed_back_charges_count": len(disputed_bcs),
        "cutoff_days": 7,
    }

# ---------------- Crew Dispatch Board ----------------
@api_router.get("/dispatch")
async def get_dispatch(user: User = Depends(get_current_user)):
    # Tomorrow window (UTC-based). We treat "tomorrow" as start-of-tomorrow to end-of-tomorrow UTC.
    now = utcnow()
    start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    cursor = db.crew_assignments.find(
        {"user_id": user.user_id, "date": {"$gte": start, "$lt": end}},
        {"_id": 0},
    )
    rows = await cursor.to_list(200)
    # Group by crew
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["crew"], []).append(CrewAssignment(**r).model_dump(mode="json"))
    ordered = [{"crew": crew, "assignments": sorted(items, key=lambda x: x["date"])} for crew, items in sorted(groups.items())]
    return {"date": start.isoformat(), "crews": ordered, "total": len(rows)}

@api_router.post("/dispatch", response_model=CrewAssignment)
async def create_dispatch(payload: CrewAssignmentCreate, user: User = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    dsp = CrewAssignment(user_id=user.user_id, job_name=job["name"], **payload.model_dump())
    await db.crew_assignments.insert_one(dsp.model_dump())
    return dsp

# ---------------- End of Day Checkin ----------------
@api_router.post("/checkin/start")
async def checkin_start(user: User = Depends(get_current_user)):
    jobs = await db.jobs.find({"user_id": user.user_id, "status": "active"}, {"_id": 0}).to_list(50)
    if not jobs:
        raise HTTPException(400, "No active jobs")
    session = CheckinSession(user_id=user.user_id, job_ids=[j["id"] for j in jobs])
    await db.checkin_sessions.insert_one(session.model_dump())
    return {
        "checkin_id": session.id,
        "total_jobs": len(jobs),
        "current_index": 0,
        "current_job": jobs[0],
    }

@api_router.post("/checkin/answer")
async def checkin_answer(payload: CheckinAnswerRequest, user: User = Depends(get_current_user)):
    session_doc = await db.checkin_sessions.find_one(
        {"id": payload.checkin_id, "user_id": user.user_id}, {"_id": 0},
    )
    if not session_doc:
        raise HTTPException(404, "Checkin not found")

    # Record answer as chat log
    job_doc = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
    job_display = job_doc["name"] if job_doc else payload.job_id
    log_text = f"[End-of-Day · {job_display}] Completed: {payload.completed or '—'}. Issues: {payload.issues or 'none'}"
    await db.chat_messages.insert_one(
        ChatMessage(user_id=user.user_id, role="user", content=log_text).model_dump()
    )
    # If issues mention "fail" or "inspection", create failed inspection draft
    if payload.issues and any(k in payload.issues.lower() for k in ["fail", "inspection"]):
        job = await db.jobs.find_one({"id": payload.job_id, "user_id": user.user_id}, {"_id": 0})
        if job:
            ins = Inspection(
                user_id=user.user_id, job_id=payload.job_id, job_name=job["name"],
                inspection_type="Daily Check", result="fail", notes=payload.issues,
            )
            await db.inspections.insert_one(ins.model_dump())

    answered = list(session_doc.get("answered", []))
    if payload.job_id not in answered:
        answered.append(payload.job_id)
    job_ids = session_doc["job_ids"]
    remaining_ids = [j for j in job_ids if j not in answered]

    update = {"answered": answered}
    result = {"checkin_id": payload.checkin_id, "answered_count": len(answered), "total_jobs": len(job_ids)}

    if remaining_ids:
        next_job = await db.jobs.find_one({"id": remaining_ids[0], "user_id": user.user_id}, {"_id": 0})
        result["current_job"] = next_job
        result["done"] = False
    else:
        # Complete + LLM summary
        completed_at = utcnow()
        summary = "Day wrapped up. Nice work."
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            # Gather all EOD chat logs from this session (job order)
            logs = []
            all_msgs = await db.chat_messages.find(
                {"user_id": user.user_id, "role": "user", "content": {"$regex": "^\\[End-of-Day"}},
                {"_id": 0}
            ).sort("created_at", -1).to_list(len(job_ids))
            for m in reversed(all_msgs[:len(job_ids)]):
                logs.append(m["content"])
            ctx = "\n".join(logs)
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"eod_{user.user_id}_{payload.checkin_id}",
                system_message=(
                    "You are SubSidekick. Given a foreman's end-of-day report per job, write a "
                    "short 3-4 sentence summary for the office. Plain-spoken, no bullets. "
                    "Highlight anything that failed or needs follow-up."
                ),
            ).with_model("openai", "gpt-5.4-mini")
            resp = await chat.send_message(UserMessage(text=ctx))
            summary = resp if isinstance(resp, str) else str(resp)
        except Exception:
            logger.exception("EOD summary failed")
        update["completed_at"] = completed_at
        update["summary"] = summary
        result["done"] = True
        result["summary"] = summary

    await db.checkin_sessions.update_one({"id": payload.checkin_id}, {"$set": update})
    return result

# ---------------- Voice: transcribe + TTS ----------------
@api_router.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty audio")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio too large")
    suffix = Path(file.filename or "audio.m4a").suffix.lower() or ".m4a"
    if suffix not in {".m4a", ".mp3", ".wav", ".webm", ".mp4"}:
        suffix = ".m4a"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        Path(tmp_path).write_bytes(data)
        try:
            from emergentintegrations.llm.openai import OpenAISpeechToText
            stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
            result = stt.transcribe(tmp_path)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, str):
                text = result
            else:
                text = getattr(result, "text", None) or (result.get("text") if isinstance(result, dict) else "")
        except Exception as e:
            logger.exception("STT failed")
            raise HTTPException(502, f"Transcription failed: {e}")
        return {"text": text.strip()}
    finally:
        Path(tmp_path).unlink(missing_ok=True)

class TTSRequest(BaseModel):
    text: str
    voice: str = "onyx"

@api_router.post("/voice/tts")
async def voice_tts(payload: TTSRequest, user: User = Depends(get_current_user)):
    key = hashlib.sha256(f"{payload.text}|{payload.voice}|tts-1|mp3".encode()).hexdigest()
    cached = await db.tts_cache.find_one({"key": key}, {"_id": 0})
    if cached:
        return {"key": key, "url": f"/api/voice/audio/{key}.mp3"}
    try:
        from emergentintegrations.llm.openai import OpenAITextToSpeech
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio_bytes = await tts.generate_speech(
            text=payload.text[:4000], model="tts-1", voice=payload.voice
        )
    except Exception as e:
        logger.exception("TTS failed")
        raise HTTPException(502, f"TTS failed: {e}")
    # Persist to disk (simple local cache)
    cache_dir = Path("/tmp/tts_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / f"{key}.mp3"
    file_path.write_bytes(audio_bytes)
    await db.tts_cache.insert_one({"key": key, "path": str(file_path), "created_at": utcnow()})
    return {"key": key, "url": f"/api/voice/audio/{key}.mp3"}

@api_router.get("/voice/audio/{key}.mp3")
async def voice_audio(key: str):
    doc = await db.tts_cache.find_one({"key": key}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Audio not found")
    path = Path(doc["path"])
    if not path.exists():
        raise HTTPException(404, "Audio missing")
    return Response(content=path.read_bytes(), media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=31536000"})

# ---------------- Root ----------------
@api_router.get("/")
async def root():
    return {"service": "subsidekick", "status": "ok"}

# ---------------- App wiring ----------------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id", unique=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    except Exception as e:
        logger.warning(f"Index create failed: {e}")
    # Initialize object storage (best-effort; ignore if unavailable)
    try:
        await run_in_threadpool(_init_storage_sync)
        logger.info("Object storage initialized")
    except Exception as e:
        logger.warning(f"Object storage init failed: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
