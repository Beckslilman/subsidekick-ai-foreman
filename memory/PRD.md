# SubSidekick — Product Requirements

## Overview
Voice-first AI foreman mobile app for small subcontractors. Superintendents talk to an AI on their phone; the AI captures change orders, back charges, failed inspections, and daily progress as structured drafts for the office to review.

## Target Users
- **Field / Superintendent**: Blue-collar, tech-averse, works from a truck. Uses voice.
- **Office / Admin**: Reviews drafts, approves change orders, disputes back charges.

## Features Delivered
### MVP (Iteration 1)
- Google OAuth (Emergent) + demo mode
- Morning Briefing (LLM-generated, GPT-5.4-mini)
- Voice Chat: press-and-hold record → Whisper → GPT-5.4-mini → OpenAI TTS
- Auto-draft change orders and back charges from chat content
- Jobs & Crews list with progress bars
- Job Detail with change orders, back charges, inspections
- Office Digest with Approve/Reject actions

### Iteration 2
- End of Day Check-in (guided per-job walk-through with LLM summary)
- Photo Attach (Emergent Object Storage → embedded in draft)
- Missed Money Radar widget on Home
- Crew Dispatch Board (tomorrow, grouped by crew)

### Iteration 3
- **Voice Kick Off**: say "wrap it up" (or similar) in Talk → auto-routes to /checkin
- **Photo Camera**: SNAP button next to GALLERY on Talk uses expo-image-picker `launchCameraAsync`
- **Dispatch Editor**: tap any assignment card → modal to switch crew or move to a different job (PATCH /api/dispatch/{id})
- **Weekly Recovery Text**: Twilio SMS on Mondays 8 AM UTC (APScheduler cron). Settings screen for phone + opt-in. Manual "Send Test Text Now" button. Falls back to sms_outbox collection if Twilio env vars are blank.

## Tech Stack
- Frontend: Expo Router, TanStack Query, expo-audio, expo-image-picker, MDI icons, expo-secure-store
- Backend: FastAPI + Motor (MongoDB), APScheduler (weekly cron), Twilio SMS
- AI: emergentintegrations (LlmChat GPT-5.4-mini, Whisper, OpenAI TTS)
- Auth: Emergent Google Auth (+ demo mode)
- Storage: Emergent Object Storage (photos), MongoDB (everything else)

## Design
Brutalist industrial: high-contrast black/white with Industrial Orange (#FF5A00), thick 2pt black borders, no shadows, 56pt+ touch targets, walkie-talkie mic hero.

## Env Vars
- Backend `.env`: `EMERGENT_LLM_KEY`, `MONGO_URL`, `DB_NAME`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- Twilio vars are optional — with them blank, weekly text falls back to `sms_outbox` collection so nothing breaks and messages can be reviewed later.
