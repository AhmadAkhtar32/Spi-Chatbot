# SPI Assistant — Step 2 Prototype

A working, end-to-end pipeline: chat UI &rarr; FastAPI backend &rarr; Claude
(function calling) &rarr; placeholder business functions. This matches
Atif's plan: it's the "temporary interface to test the pipeline" — not
the final PowerBuilder integration (that's Steps 3&ndash;5).

```
spi-chatbot/
├── backend/
│   ├── app.py                 # FastAPI server + Claude function-calling loop
│   ├── business_functions.py  # placeholder check_stock / get_order_status / find_menu_location
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── index.html             # chat UI (no build step — plain HTML/CSS/JS)
```

## Run it

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # then open .env and paste your real Claude key when you have it
uvicorn app:app --reload
```

Open **http://localhost:8000** in your browser. FastAPI serves both the
API and the chat UI, so this one command is all you need.

**Before you have a key:** it still runs — the UI, backend, and sidebar
all work, and the chat will reply with "Demo mode: no ANTHROPIC_API_KEY is
set yet" so you can show the pipeline is wired up correctly.

**Once you add your key** to `.env`, the same UI will call the real
Claude model, and you'll see live function-call traces (small tags like
`check_stock(item='Pepsi')`) appear above each answer — this is
deliberate: it visually proves the AI only ever goes through your
approved functions, never straight to the database, which is exactly
the access-control point Atif needs to see.

## What to try once it's live
- "What's the stock of Pepsi?"
- "What's the status of order #1234?"
- "Where do I add stock?" (business-navigation question)

## Notes for next steps
- Swapping placeholder data for real data: edit `business_functions.py`
  only — each function has a `TODO` marking exactly where the real
  `cx_Oracle` / `pyodbc` query goes. Nothing else needs to change.
- Sidebar modules (Sales, Purchase, Finance, Payroll, CRN) are shown as
  "Phase 2/3" to reflect the real phased rollout — add real tool
  definitions for each module in `app.py`'s `TOOLS` list as they come online.
- This frontend is intentionally framework-free so it runs with zero
  build step. If/when you want to convert it to React for the final
  version, the `fetch('/api/chat', ...)` call is the only logic that
  needs porting over.
