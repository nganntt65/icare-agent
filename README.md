# 🇹🇼 iCare: Cross-Cultural Agentic AI Navigator 

> **Campus Self-Proposed Group (校園自主命題組)**  
> **Theme**: Campus Administration & Service Processes (校園行政與服務流程)  
> **Team**: MaVi  

**iCare** is a cross-cultural agentic AI navigator designed to assist international students in Taiwan through administrative and campus life processes with strict safety guardrails, hybrid retrieval, and privacy compliance.

This codebase delivers the **Track 1 MVP (Support Retrieve Information First)**.

---

## 🏗️ Architecture & Core Components

```
                                  [ Inbound Student Query ]
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │  Input Guardrails Pre-flight  │
                             │  - Deterministic Crisis Check │  ──► [Fast-Path 1: Hotlines 1925/1995/1955]
                             │  - Prompt-Injection Defense   │  ──► [Fast-Path 2: Security Block]
                             │  - PII Regex Scrubbing        │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │  Multilingual NLP Normalizer  │
                             │  (VI/ID/EN/ZH -> Campus Terms)│
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │    LangGraph-Compatible FSM   │
                             │ (DISCOVERY ──► RESOURCE_MATCH)│
                             └───────────────┬───────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
         ┌─────────────────────────┐                   ┌─────────────────────────┐
         │     Dense Vector        │                   │       BM25 Inverted     │
         │   Semantic Retrieval    │                   │      Sparse Matching    │
         └────────────┬────────────┘                   └────────────┬────────────┘
                      │                                             │
                      └──────────────────────┬──────────────────────┘
                                             ▼
                             ┌───────────────────────────────┐
                             │ Reciprocal Rank Fusion (RRF)  │
                             │   Score: sum(1 / (60 + rank)) │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │   Model Synthesis Engine      │
                             │  (Gemini Flash / Grounded)    │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │  Faithfulness & Citation      │
                             │  Auditor (Score >= 0.85)      │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │ Ephemeral 30-min Session Cache│
                             │  + Web UI & REST API Egress   │
                             └───────────────────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Run the Server
From the project directory:
```bash
python3 run.py --port 8000
```

### 2. Access the Interactive Web Interface
Open your browser to:
👉 **[http://localhost:8000/](http://localhost:8000/)**

The Web UI features:
- **Interactive Chat Interface** with quick-test preset scenario buttons.
- **Live FSM & Retrieval Inspector** showing state transitions (`DISCOVERY` ➔ `SAFETY_EVALUATED` ➔ `RESOURCE_MATCHED` ➔ `COMPLETED`).
- **Data Minimization Box**: Live view of redacted ARC and phone numbers.
- **Verified Citations**: Institutional source document, section, and RRF score.
- **Session Purge Button**: `/forget` memory eviction under Taiwan PDPA.

---

## 🧪 Running Automated Tests

Run the full benchmark test suite (34 unit & scenario integration tests):
```bash
python3 -m unittest discover tests -v
```

All tests execute in under 0.1s with zero external network dependencies!

---

## 📁 Project Directory Layout

```
icare-agent/
├── data/
│   ├── raw_documents/                  # Decoupled campus policy files
│   │   ├── arc_procedures.md           # ARC 30-day window, documents, NIA address
│   │   ├── nhi_insurance.md            # NHI 6-month rule, NT$826 fee, card pickup
│   │   ├── housing_dormitories.md      # Dorm check-in, deposit, 23:00 curfew
│   │   ├── course_selection.md         # Stage 1-2, add/drop, instructor override (加簽)
│   │   └── health_exam.md              # Form B exam items, designated hospitals
│   ├── official_services.json          # University services registry config
│   └── document_hashes.json            # SHA-256 cryptographic manifest for sub-second starts
├── src/
│   ├── security/
│   │   ├── crisis_detector.py          # Deterministic crisis interception (1925/1995/1955)
│   │   ├── prompt_injection.py         # Jailbreak & DAN defense
│   │   └── pii_scrubber.py             # ARC & phone number regex sanitizer
│   ├── nlp/
│   │   ├── language_detector.py        # EN, VI, ID, ZH language identifier
│   │   └── cross_lingual_normalizer.py # Colloquial term normalizer (e.g. thẻ cư trú -> ARC)
│   ├── retrieval/
│   │   ├── document_indexer.py         # Markdown section parser & SHA-256 validator
│   │   ├── bm25_retriever.py           # Pure-Python BM25Okapi sparse engine
│   │   ├── vector_retriever.py         # Dense semantic vector search & cosine similarity
│   │   └── hybrid_rrf.py               # Reciprocal Rank Fusion combiner (k=60)
│   ├── memory/
│   │   └── session_memory.py           # 30-min TTLCache ephemeral session manager
│   ├── agent/
│   │   ├── state.py                    # Typed AgentState & FSMStateEnum
│   │   ├── citation_auditor.py         # Grounding & citation auditor (threshold 0.85)
│   │   └── fsm_engine.py               # Orchestrator & FastPathRouter
│   └── server/
│       ├── http_server.py              # Multi-threaded HTTP REST API
│       └── static/                     # Web UI (index.html, style.css, app.js)
├── tests/
│   ├── test_security.py                # Security & guardrail unit tests
│   ├── test_nlp.py                     # NLP & cross-lingual unit tests
│   ├── test_retrieval.py               # BM25, Vector, and RRF unit tests
│   ├── test_fsm_agent.py               # FSM lifecycle & auditor unit tests
│   ├── test_server.py                  # API endpoints unit tests
│   └── test_scenarios.py               # End-to-end operational scenario benchmarks
├── run.py                              # Application entry launcher
└── requirements.txt                    # Python dependency manifest
```

---

## 📡 REST API Reference

### 1. Send Message (`POST /api/chat`)
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "message": "My ARC expires in three days. What documents do I need from the school?"
  }'
```

### 2. Purge Session Memory (`POST /api/forget`)
```bash
curl -X POST http://localhost:8000/api/forget \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test_session"}'
```

### 3. System Health & Documents Status (`GET /api/health`)
```bash
curl http://localhost:8000/api/health
```

### 4. Official Services Registry (`GET /api/services`)
```bash
curl http://localhost:8000/api/services
```

---

## 📱 LINE Messaging API Integration Guide

iCare is fully equipped to interact with real students through a **LINE Official Account**.

### 1. Retrieve LINE Developer Credentials
1. Open the [LINE Developers Console](https://developers.line.biz/console/).
2. Select your Provider & Messaging API Channel.
3. In the **Basic settings** tab, copy your **Channel Secret**.
4. In the **Messaging API** tab, issue and copy the **Channel access token (long-lived)**.
5. In your project directory, add them to `.env`:
   ```bash
   LINE_CHANNEL_SECRET=your_channel_secret_here
   LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token_here
   ```

### 2. Expose Localhost to Public HTTPS
LINE requires a secure HTTPS webhook URL. You can use **ngrok** or **Cloudflare Tunnel**:
```bash
# Option A: ngrok
brew install ngrok
ngrok http 8000

# Option B: cloudflared (free, no sign-up needed)
brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```
Copy the generated public HTTPS URL (e.g. `https://xxxx-xx-xx.ngrok-free.app`).

### 3. Set Webhook in LINE Developers Console
1. In the **Messaging API** tab:
   - **Webhook URL**: Enter `https://your-public-domain/api/webhook/line` (or `/callback`)
   - Click **Verify** (displays "Success").
   - Enable **Use webhook**.
2. In **LINE Official Account features** -> **Auto-reply messages**:
   - Set Auto-reply messages to **Disabled** (so the default LINE auto-responder doesn't collide with iCare).

### 4. Local LINE Simulator (No Tunnel Required)
You can test LINE webhook dispatching immediately from your terminal:
```bash
# Test routine ARC inquiry with automatic Calendar action proposal
python3 simulate_line_message.py --text "My ARC expires in three days. Can you schedule a reminder on Google Calendar?"

# Test postback confirmation (Two-Phase Commit Gate execution)
python3 simulate_line_message.py --postback "action=confirm&proposal_id=PROP-CAL-1234&token=abcd"

# Test postback cancellation (immediate rollback)
python3 simulate_line_message.py --postback "action=cancel&proposal_id=PROP-CAL-1234"

# Test multilingual Vietnamese inquiry
python3 simulate_line_message.py --text "Làm thế nào để gia hạn thẻ cư trú?"

# Test new friend follow event
python3 simulate_line_message.py --follow

# Test crisis intervention card
python3 simulate_line_message.py --crisis
```

---

## ⚡ Next Phase: Action Execution & Human-in-the-Loop (HITL) Gate

As specified in **Proposal Sections 5, 6, 7 & 10**, iCare bridges information with action using a **Two-Phase Commit Gate**:

```
[Inbound Query] ──► [Hybrid Retrieval & Grounding]
                           │
                           ▼
               [Action Intent Detected]
                           │
                           ▼
          Phase 1: [ActionProposal (PROP-XXX)]
          (Generates proposal ID & secret confirmation token)
                           │
                           ▼
             [LINE Postback / User Prompt Gate]
             ┌─────────────┴─────────────┐
             ▼                           ▼
      [Student Confirms]          [Student Cancels]
             │                           │
  Phase 2: [Verify Token]           [Rollback State]
             │                     (Zero mutations)
             ▼
    [Execute Tool Layer]
    ├─ Google Calendar Sync (Live API / Sandbox URL)
    ├─ Campus Webhook (2x Retry -> Fallback Walk-in)
    └─ Pre-filled Email Referrals
             │
             ▼
    [Issue Official Alphanumeric Receipt]
    (REC-SCH-XXXX with SHA-256 Consent Proof)
```

### Supported Action Tools
1. **Google Calendar Sync (`calendar_tool.py`)**:
   - Live Mode: Creates calendar events via Google Calendar API v3 when OAuth token is set in `.env`.
   - Sandbox Mode: Renders valid 1-click Google Calendar web event creation URLs with pre-filled title, dates, checklist, and location.
2. **Campus Webhook Intake (`campus_webhook_tool.py`)**:
   - Dispatches structured intake bookings to institutional endpoints (`CAMPUS_WEBHOOK_URL`).
   - Upstream Failure Resilience: Catches HTTP 5xx/timeouts and retries twice.
   - Fallback Recovery: Upon persistent failure, automatically generates walk-in office navigation (Administration Building, Room 201) and pre-filled email draft.
3. **Pre-filled Email & Walk-in Referral (`email_draft_tool.py`)**:
   - Generates 1-click `mailto:` links with pre-filled subject, required physical documents checklist, and office hours.
4. **Alphanumeric Receipt Emitter (`receipt_emitter.py`)**:
   - Generates immutable `REC-SCH-XXXX` receipts with cryptographic consent proofs logged to audit records.

---

## 🛡️ Safety & Governance
- **Non-Diagnostic Boundaries**: iCare strictly prohibits psychological diagnoses or drug dosage suggestions and routes to Campus Health or Counseling Center.
- **Emergency Crisis Escalation**: Detects crisis keywords in EN, VI, ID, ZH and deterministically presents Taiwan emergency hotlines (1925, 1995, 1955, and Campus Security).
- **Two-Phase Commit Human Gate**: Under Taiwan PDPA, zero external tool calls or mutations occur without explicit student confirmation tokens.
- **Data Minimization**: Taiwan ARC numbers and phone numbers are scrubbed prior to retrieval.
- **Privacy Compliance**: Ephemeral 30-minute memory with instant purge via `/forget`. Zero cross-session user profiling.
