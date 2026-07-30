# SPI AI Assistant — Enterprise Workspace

React + Tailwind + Framer Motion frontend, built as an AI Workspace
(dashboard-first) rather than a plain chat window, per the latest brief.

```
src/
├── App.jsx                          # view state machine: workspace <-> chat
├── index.css
└── components/
    ├── Navbar.jsx                   # logo, module badge, avatar
    ├── Workspace.jsx                 # home dashboard container
    │   ├── WelcomeSection.jsx        # time-aware greeting
    │   ├── ModuleCard.jsx            # Inventory/Sales/Purchase/Finance/Payroll/Navigation
    │   └── PopularTask.jsx           # quick example queries
    ├── ChatWindow.jsx                # message list + Back to Workspace
    │   └── ChatMessage.jsx           # markdown, tables, status badges, copy, timestamp
    ├── TypingIndicator.jsx
    ├── StatusBadge.jsx
    ├── BackToWorkspaceButton.jsx
    └── MessageInput.jsx              # always pinned at the bottom of the app
```

## Run it (two terminals)

**Terminal 1 — backend:**
```powershell
cd spi-chatbot\backend
python -m uvicorn app:app --reload
```

**Terminal 2 — frontend:**
```powershell
cd spi-chatbot-react
npm install
npm run dev
```

Open **http://localhost:5173**.

## How the workspace behaves
- **On load:** you see the Workspace — greeting, six module cards
  (Inventory, Sales, Purchase, Finance, Payroll, ERP Navigation), and a
  Popular Tasks list. No blank chat screen.
- **Clicking a module card** immediately starts a conversation scoped to
  that module (workspace transitions out, chat transitions in) and
  updates the top-right module badge, e.g. "Inventory Module".
- **Clicking a Popular Task** switches to the chat screen and pre-fills
  the input with that task's text — it does not send automatically, so
  you can edit before submitting.
- **The bottom input bar is always present**, on both the Workspace and
  Chat screens — you can type a question at any time, from anywhere.
- **"← Back to Workspace"** appears at the top of the chat screen.
  Clicking it returns to the dashboard *without* clearing the
  conversation — all messages stay in React state, so reopening chat
  (via any card, task, or the input) continues right where you left off.
- **Assistant replies** render full markdown — bold, bullet lists,
  tables, fenced code blocks — and automatically convert recognized
  status words ("Shipped," "Out of Stock," "Processing," etc.) into
  small colored badges. Each assistant message has a hover-to-reveal
  copy button and a timestamp.

Works immediately even without a Claude key — you'll see a "Demo mode"
reply confirming the pipeline (React → FastAPI → Claude function
calling) is wired correctly end to end. Add your key to
`spi-chatbot/backend/.env` and restart the backend for live answers
with real function-call traces.

## Production build
```powershell
npm run build
```
Outputs to `dist/`. Point FastAPI's `StaticFiles` mount in
`spi-chatbot/backend/app.py` at this folder to serve the built app from
the same origin as the API.
