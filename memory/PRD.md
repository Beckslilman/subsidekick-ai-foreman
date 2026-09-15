# SubSidekick — Product Requirements

## Overview
Voice-first AI foreman mobile app for small subcontractors ($2-10M revenue, 2-3 crews). Superintendents talk to an AI on their phone; the AI captures change orders, back charges, failed inspections, and daily progress as structured drafts for the office to review.

## Target Users
- **Field / Superintendent**: Blue-collar, tech-averse, works from a truck. Uses voice.
- **Office / Admin**: Reviews drafts, approves change orders, disputes back charges.

## Features Delivered
### MVP (Iteration 1)
- Google OAuth (Emergent-managed) + demo mode
- Morning Briefing (LLM-generated, GPT-5.4-mini)
- Voice Chat with AI Foreman — press-and-hold record (expo-audio) → Whisper → GPT-5.4-mini → OpenAI TTS
- Auto-draft creation for change orders / back charges from chat content
- Jobs & Crews list with progress bars
- Job Detail view with change orders, back charges, inspections
- Office Digest with Approve/Reject actions
- Seeded demo data

### Iteration 2 (added)
- **End of Day Check-in**: Guided flow that walks through each active job, captures completed work + issues, auto-logs failed inspections, and gives the office an LLM-generated day summary
- **Photo Attach**: Field super picks a photo from gallery (expo-image-picker), uploads to Emergent Object Storage, and attaches it to the next chat message → embedded in the created draft
- **Missed Money Radar**: Widget on Home totaling unsigned change orders + disputed back charges older than 7 days ($5,050 for demo user)
- **Crew Dispatch Board**: Tomorrow's crew assignments grouped by crew name with per-assignment time, job, and notes

## Tech Stack
- Frontend: Expo Router, TanStack Query, expo-audio, expo-image-picker, MDI icons, expo-secure-store
- Backend: FastAPI + Motor (MongoDB)
- AI: emergentintegrations (LlmChat GPT-5.4-mini, OpenAISpeechToText Whisper, OpenAITextToSpeech tts-1)
- Auth: Emergent Google Auth
- Storage: Emergent Object Storage (`INTEGRATION_PROXY_URL` + `EMERGENT_LLM_KEY`) for photos; MongoDB for everything else

## Design
Brutalist industrial: high-contrast black/white with Industrial Orange (#FF5A00), thick 2pt black borders, no shadows, 56pt+ touch targets, oversized walkie-talkie mic button.
