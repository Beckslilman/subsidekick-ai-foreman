# SubSidekick — Product Brief (locked)

This file is the product source of truth for this repository. Do not invent competing scope. Historical office-dashboard notes in `memory/PRD.md` must not override this brief.

## Stack decision

- **This repo is the single code home.**
- **Deploy target:** Vercel (frontend + backend) + Supabase project **subsidekick** (ref `vbcyzvlyfzapnifqrwlf`).
- **Emergent is PARKED.** Do not treat Emergent as the primary deploy path, and do not add Emergent-specific deploy docs as primary.

## Personas / features (light UX)

### 1. Foreman / field (phone-first)

- Morning + anytime **call or text**.
- Favorites for their crews.
- If they open the app at all: only **schedule**, **jobsite notes** (materials delivered, inspection dates), and **open flags**.
- Photo for jobs / COs / backcharges.
- Ask about uploaded plans, drawings, research notes, and codes.
- **Everything money = DRAFT ONLY.**

### 2. Sarah / office

- Setup crews, jobs, supers, phones.
- Assign favorites.
- Upload plans / codes.
- Daily digest.
- Approve / edit / reject drafts.
- **Only office / owner can release invoice-related actions.**

### 3. Owner dashboard

Not a maze. Surface:

- extras / COs
- backcharges
- schedule
- billing / late invoices
- cash pulse

### 4. Gumroad ToolBox kit

Capabilities fold into **voice / text**. They are not separate products.

## Non-negotiable

**DRAFT ONLY** for change orders, invoices, and backcharges until a human approves. The AI never sends money documents on its own.

## Build order

1. Voice / text loop + drafts + photos + Sarah setup + owner digest
2. Plans / codes Q&A + invoice drafts + late invoice
3. Leads depth, QuickBooks, Spanish — later

## GHL

- Voice AI agent: **SubSideKick Foreman Check-In**
- Number: **+1 229 585 7126** (`+12295857126`)
- Webhooks must target the **live Vercel backend** once healthy — not Emergent preview URLs.

Webhook path on this FastAPI app: `/api/webhooks/ghl/voice-ai`.

## Fold notes

Current deploy wiring, Mongo vs Supabase gap, and the live Vercel 500 investigation live in [docs/STACK.md](./docs/STACK.md).
