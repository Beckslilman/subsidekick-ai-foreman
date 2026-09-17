# SubSidekick stack — known state (2026-09-17)

Product lock: [PRODUCT.md](../PRODUCT.md). This file is the fold path, not a second product brief.

## Target (locked)

| Piece | Target |
| --- | --- |
| Code home | This repo (`Beckslilman/subsidekick-ai-foreman`) |
| Frontend + backend host | Vercel |
| Database | Supabase project **subsidekick**, ref `vbcyzvlyfzapnifqrwlf` (`https://vbcyzvlyfzapnifqrwlf.supabase.co`) |
| Emergent | **PARKED** — not the primary deploy, no Emergent-specific deploy docs as primary |

Live URLs to keep using after the fold:

- Frontend: `https://subsidekick-frontend.vercel.app`
- Backend: `https://subsidekick-backend.vercel.app`
- GHL webhooks (once backend is healthy): `https://subsidekick-backend.vercel.app/api/webhooks/ghl/voice-ai` (and SMS siblings under `/api/webhooks/...`) — **not** Emergent preview hosts.

## Verified 2026-09-17

### Vercel frontend — live

`https://subsidekick-frontend.vercel.app` returns **HTTP 200**.

It is still an Emergent-exported SPA (`emergent.sh` scripts, `static/js/main.*.js`), **not** this repo’s Expo app under `frontend/`. The production JS bundle talks to `https://subsidekick-backend-git-main-cbm7.vercel.app`, not a Supabase URL.

### Vercel backend — 500

Probed:

- `https://subsidekick-backend.vercel.app/` → **500** `FUNCTION_INVOCATION_FAILED`
- `https://subsidekick-backend.vercel.app/api` → **500** `FUNCTION_INVOCATION_FAILED`
- `https://subsidekick-backend.vercel.app/api/health` → **500** `FUNCTION_INVOCATION_FAILED`
- `https://subsidekick-backend.vercel.app/docs` → **500**
- `https://subsidekick-backend-git-main-cbm7.vercel.app` (same paths) → **500** `FUNCTION_INVOCATION_FAILED`

A 500 on every path, including ones this FastAPI does not define (`/api/health` before this fold, `/docs` if the process never starts), means the **serverless function is crashing on boot**, not a single broken route.

Vercel MCP listed projects `subsidekick-backend` (`prj_oQDOXm4E4xpOQVqx20yL11lyEOfD`) and `subsidekick-frontend` (`prj_gZIosSEIZQeLcgRlUyGuIVGIn8c0`) as Git-linked to **`Beckslilman/subsidekick`**, not this repo. Runtime logs / project env could not be read (team scope `cbm7` 403). Treat that Git link as part of the fold: relink both Vercel projects to **this** repo.

### Supabase — healthy

Project **subsidekick** (`vbcyzvlyfzapnifqrwlf`) is `ACTIVE_HEALTHY` in `us-east-1`. Public tables present (RLS on):

`companies`, `profiles`, `company_members`, `crews`, `jobs`, `field_users`, `field_records`, `change_order_drafts`, `back_charge_flags`, `schedule_change_requests`, `daily_digests`, `conversation_messages`, `integration_settings`, `webhook_events`

Money tables (`change_order_drafts`, `back_charge_flags`) default to `needs_review`. That matches **DRAFT ONLY until human approve**. Do not add auto-send.

This FastAPI codebase does **not** read or write those tables yet.

### This repo’s backend storage — Mongo, not Supabase

`backend/server.py` is FastAPI + **Motor / MongoDB**.

- Import used to require `MONGO_URL` and `DB_NAME` (`os.environ['MONGO_URL']`). Missing either is a **boot crash** (`KeyError`) — the same class of failure as Vercel `FUNCTION_INVOCATION_FAILED`.
- There is **no** `supabase` client, URL, or table access in this API.
- Collections in use: `users`, `user_sessions`, `jobs`, `team_members`, `change_orders`, `back_charges`, `schedule_changes`, `inspections`, `call_logs`, `crew_assignments`, `chat_messages`, `checkin_sessions`, `uploads`, `sms_outbox`, `ghl_events`, `twilio_inbound_sids`.

Those Mongo names do **not** match the Supabase schema. Fold is a later mapping job, not a same-day cutover.

## 500 hypothesis (verified against this repo; live env unread)

Hypothesis given: backend 500 is missing env (Supabase URL/keys **or** Mongo).

| Claim | Result |
| --- | --- |
| Missing `MONGO_URL` / `DB_NAME` crashes **this** FastAPI on import | **Kept.** Code did `os.environ['MONGO_URL']` / `os.environ['DB_NAME']` at module load. |
| Missing Supabase URL/keys crashes **this** FastAPI | **Discarded for this codebase.** No Supabase imports or env reads on the request path. |
| Live Vercel 500 is *proven* to be missing Mongo on the currently deployed app | **Unproven.** Function crash-on-boot matches, but the Vercel Git source is `Beckslilman/subsidekick` (not this repo) and env/logs were not readable. Could still be missing Mongo, a different boot exception, or a different entrypoint. |

After this fold PR, `/api/health` reports whether Mongo and Supabase **env vars are present** (booleans only, no secrets) without crashing the process when Mongo is unset. Data routes return **503** until Mongo is configured (Supabase is still unused).

## Small fold steps (this PR and next)

**This PR (safe, no route rewrite, money draft-only unchanged):**

1. Lock product in `PRODUCT.md`; point `README.md` at it.
2. Document the Mongo ↔ Supabase gap here.
3. `backend/env.example` — current Mongo vars + target Supabase vars (unused by routes).
4. `backend/env_config.py` + `/api/health` so missing Mongo no longer KeyErrors the whole function.
5. `backend/vercel.json` — FastAPI `server.py` function config for when Vercel Root Directory = `backend`.

**Do not do in this PR:** swap Motor for Supabase, change draft/approve behavior, retarget GHL in HighLevel, or write Emergent deploy docs.

**Next (human / follow-up), in order:**

1. Relink Vercel `subsidekick-frontend` and `subsidekick-backend` from `Beckslilman/subsidekick` → `Beckslilman/subsidekick-ai-foreman`.
   - Backend Root Directory: `backend` (entrypoint `server.py`, FastAPI instance `app`).
   - Frontend Root Directory: `frontend` (Expo web). Today’s live frontend is still the Emergent SPA.
2. Set backend env: `MONGO_URL`, `DB_NAME` (required for current routes), plus GHL/Twilio/LLM secrets already used. Optionally set `SUPABASE_URL` + service/publishable keys so `/api/health` shows `supabase_env_present: true` before any query fold.
3. Confirm `GET https://subsidekick-backend.vercel.app/api/health` is **200**, then point GHL Voice AI + SMS webhooks at that host (not Emergent previews, not `*-git-main-*.vercel.app` once production is healthy).
4. Later: map FastAPI collections onto the existing Supabase tables without auto-releasing money documents.

## Env (names only)

See `backend/env.example`.

**Required for current FastAPI data routes**

- `MONGO_URL`, `DB_NAME`

**Fold target (documented, unused by routes today)**

- `SUPABASE_URL` = `https://vbcyzvlyfzapnifqrwlf.supabase.co`
- `SUPABASE_PUBLISHABLE_KEY` or `SUPABASE_ANON_KEY` (browser / RLS)
- `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY` (**server only**, never the Expo/web client)

**Already used by this API (unchanged)**

- `GHL_ACCESS_TOKEN`, `GHL_LOCATION_ID`, `GHL_PUBLIC_KEY`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` / `TWILIO_FROM_NUMBER`
- LLM key currently read as `EMERGENT_LLM_KEY` (parked vendor; do not add Emergent deploy docs)

## GHL reminder

Agent **SubSideKick Foreman Check-In** on `+12295857126`. Webhooks → live Vercel backend once `/api/health` is healthy.
