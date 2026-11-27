# CampusOS Frontend Prototype (Member 2 Workspace)

> **Important Agentware Rule Reminder:** The official 72-hour build window runs **Nov 27, 18:00 UTC – Nov 30, 18:00 UTC**. Do **not** commit pre-written code to your submission repository before kickoff; use this prototype as your local UI/UX reference & API contract preview, then initialize and commit your submission cleanly inside the hackathon window.

## Quick Start
```bash
npm install
npm run dev
```
Open `http://localhost:5173`.

## Switching to Member 1's FastAPI Backend
By default (`VITE_API_MODE=mock`), every button (`Run Scrape Now`, `Kill Switch`, `Trap Pack Simulator`, `Student Profile Re-Scoring`, `Export Digest`, `Export Trace JSON`) runs via an in-browser deterministic autonomous simulation engine.

When Member 1 exposes FastAPI on `http://localhost:8000` with endpoints defined in `src/services/api.ts`:
- `GET /api/health`
- `GET/PUT /api/profile`
- `GET/POST /api/sources`
- `GET /api/opportunities`
- `POST /api/runs/start`, `POST /api/runs/kill`, `GET /api/runs/status`
- `GET /api/audit`

Click **"Demo Engine (Standalone)"** in the top header or set `VITE_API_MODE=fastapi` in `.env`.
