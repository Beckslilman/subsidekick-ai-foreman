# SubSidekick — Product Requirements

## Vision (v4 pivot)
Voice-first AI foreman for small subcontractors. Field supers **call or text** the 24/7 AI hotline **+1 (229) 585-7126** (or receive an outbound morning briefing call). The mobile app is the **Office Dashboard** — the office admin (owner/spouse/bookkeeper) reviews drafts, approves change orders, resolves back charges, confirms schedule changes, and manages the team.

**Non-negotiable rule:** the AI never sends a change order or issues an invoice on its own. Every money item is a **DRAFT ONLY — NOT SENT** until a human approves it in the office view.

## Integrations
- **GHL Voice AI** — runs the phone conversation, sends post-call webhook to `/api/webhooks/ghl/voice-ai` with transcript + structured extraction (change orders, back charges, schedule changes). Ed25519 signature verified when `GHL_PUBLIC_KEY` is set. Idempotent by `callId`.
- **Twilio Voice + SMS** — hotline number **+1 (229) 585-7126**. Inbound SMS lands at `/api/webhooks/twilio/sms`, gets AI reply (GPT-5.4-mini) with full conversation history, returns TwiML, logs a `CallLog`, and auto-drafts change orders / back charges / schedule changes when detected.
- **OpenAI (via Emergent LLM key)** — GPT-5.4-mini for chat + morning briefing + EOD summary; Whisper for STT; TTS-1 for TTS.
- **Emergent Object Storage** — jobsite photos.
- **APScheduler** — Weekly Recovery SMS every Monday 8 AM UTC.

## Screens (Office Dashboard)
- **Digest (Home)**: "Morning, <name>." hero, 4 KPI cards, PREVIEW MORNING CALL block, "Needs your call" draft cards, "Crews in motion" job cards.
- **Inbox**: filter chips (All/Change Orders/Back Charges/Schedule/Inspections), draft cards with APPROVE/REJECT/RESOLVE/CONFIRM.
- **Jobs**: job list with codes (RIV/OAK/HIL), progress, crew, next milestone. Job detail shows COs/BCs/inspections.
- **Calls**: 24/7 hotline card, field team management (+ADD SUPER, BRIEF NOW, remove), recent call log with inbound/outbound/voice/sms and draft-count badges.
- **Settings**: integrations status, weekly recovery text, Twilio + GHL setup instructions with webhook URLs.
- **Checkin / Dispatch / Job Detail**: preserved sub-screens.

## Data Model
- Users (office admins) · TeamMembers (field supers with phone/timezone/briefing time)
- Jobs · ChangeOrders · BackCharges · ScheduleChanges · Inspections
- CallLogs (inbound/outbound, voice/sms, transcript, extracted_drafts, ghl_call_id)
- CrewAssignments (dispatch board) · CheckinSessions · SmsOutbox · Uploads · GhlEvents

## Env
Backend Deployment Secrets (process env — **source of truth** for live Twilio/GHL; Settings UI does not store SID/token):
- `EMERGENT_LLM_KEY`, `MONGO_URL`, `DB_NAME`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER="+12295857126"`
- `GHL_ACCESS_TOKEN`, `GHL_LOCATION_ID`, `GHL_PUBLIC_KEY`
- Production: Twilio signatures are required when `TWILIO_AUTH_TOKEN` is set (and fail-closed in production even if it is missing). Preview tests may set `TWILIO_SKIP_SIGNATURE_CHECK=1`.
- When `GHL_PUBLIC_KEY` is set, unsigned/invalid GHL webhooks are rejected.
- `ALLOW_DEV_LOGIN=1` required for `POST /api/auth/dev-login` (off by default).

## Design
Brutalist industrial: black surfaces, Industrial Orange (#FF5A00), thick 2pt borders, no shadows, oversized numeric KPIs, tab bar with Digest/Inbox/Jobs/Calls.
