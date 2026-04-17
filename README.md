# IRIS — Intelligent Reporting & Insight System

> AI-powered BI reporting platform for banking — from natural language to published report in minutes.

Built with **Tachikoma** (event-driven agent framework) + **Qwen 3.6-Plus** (Alibaba Cloud) for the Qwen Hackathon.

---

## What it does

A bank analyst types *"Show me loan portfolio by branch for last quarter"* — IRIS interprets the query, fetches data from the warehouse, generates a professional report with SVG charts, checks compliance, and publishes it. All visible in real-time on a Kanban board.

```
User query → Interpret → Fetch (ClickHouse) → Generate report → Render charts
           → Compliance check → Human review → Publish → Auto-file
```

## User Journey — Step by Step

### 1. Open IRIS
The analyst opens the dashboard. The sidebar shows **Agent** (chat) and **Report Status** (kanban) navigation, plus a tree of published reports and connected data sources. Everything starts empty.

### 2. Ask for a report
The analyst clicks **Agent** and types: *"Show me loan portfolio by branch for last quarter"*. Or clicks one of the preset example queries. The message is sent to the backend via `POST /api/iris/action`.

### 3. Intent detection
IRIS detects the intent — **report** (generate new) or **search** (find existing). Keyword matching routes the request:
- *"Show me loan portfolio..."* → **report** (triggers the WOT pipeline)
- *"Find reports about credit risk"* → **search** (queries Neo4j + ClickHouse + Graphiti)

### 4. A card appears on the Kanban board
For report requests, a card is created in the **To Do** column of the Kanban board. The analyst can switch to **Report Status** to watch it move through the pipeline in real-time.

### 5. Pipeline executes (7 steps, all visible)

| Step | What happens | Card moves to |
|------|-------------|---------------|
| **Interpret** | Qwen 3.6-Plus parses the query → extracts domain (`loans`), metrics (`total_disbursed`, `outstanding_balance`), dimensions (`branch`), time range (`last_quarter`). Confidence: 0.95. | Interpreting |
| **Fetch** | SQL query built automatically → `SELECT branch, avg(total_disbursed) FROM dwh.fact_loans WHERE period='2025-Q4' GROUP BY branch` → executed on ClickHouse Cloud → 8 rows returned in 50ms. | Fetching Data |
| **Generate** | Qwen generates a structured report: title, executive summary, 2-4 data sections with analysis, chart type suggestions (bar/line/pie), methodology note. Responds in the user's language. | Generating |
| **Charts** | For each section with a chart type: XML report built with `<blackbox tag="chart">` placeholders → chart sub-pipeline (elaborate → implement SVG → test → verify) → final HTML with embedded SVG charts. | Charts |
| **Compliance** | 5 banking governance rules checked: minimum data rows (DQ001), no negative monetary values (DQ002), no PII exposure (AC001), methodology mentioned (ACC001), executive summary present (ACC002). Score: 1.0, passed. | Compliance |
| **Review** | Auto-approved if compliance score ≥ 0.8. Otherwise, the card stays in Review for human decision: approve / request revision (with notes) / reject. Revision loops back to Generate (max 3 cycles). | Review |
| **Publish** | Report tracked in ClickHouse (`dwh.report_tracking`), indexed in Neo4j (graph relationships: report → department, report → charts), event published to Redpanda (`sb5.report.events`). | Published |

Each step pushes SSE events (`step.completed`, `agent.message`) — the frontend updates the chat and Kanban board in real-time.

### 6. Report auto-filed into TreeFile
After publishing, the semantic router (Qwen `text-embedding-v3` via DashScope, 1024-dim) matches the report content against folder descriptions:
- *"Loan Portfolio by Branch Q4"* → **Loan Reports / Portfolio Analysis** (cosine similarity: 0.83)

The report appears in the sidebar TreeFile under the matched folder.

### 7. Report HTML available
The generated HTML report (with embedded SVG charts, styled tables, compliance badge) is available for preview. The `report.ready` SSE event delivers the full HTML to the frontend.

### 8. Search existing reports
Later, the analyst asks: *"Find reports about credit risk"*. IRIS searches simultaneously:
- **Graphiti** (semantic) → *"Branch-C recorded an NPL ratio of 7.1% for Q4 2025"*
- **Neo4j** (graph) → reports linked to department/type
- **ClickHouse** (SQL) → `report_tracking` table fulltext match

Results are merged, deduplicated, and returned with source attribution.

### 9. Iterate
The analyst can generate more reports, each appearing on the Kanban board and auto-filing into the tree. The chat history is preserved via `ChatContextManager`. Session survives page reload (sessionStorage).

---

## Dashboard Sections

### Agent — Conversational Report Generation

The Agent panel is a chat interface connected to IRIS via SSE. Users describe what they need in natural language — IRIS detects intent (new report vs search) and executes.

**Report flow**: User asks for a report → IRIS interprets the query, builds SQL, fetches from ClickHouse, generates the report with Qwen 3.6-Plus, renders SVG charts, validates compliance, and publishes.

**Search flow**: User searches for existing reports → IRIS queries across Neo4j (graph), ClickHouse (SQL), and Graphiti (semantic embeddings) simultaneously.

Example queries:
- *"Loan portfolio by branch Q4"* → generates a full report with charts
- *"NPL ratio trends by product type"* → fetches risk data, generates analysis
- *"Find reports about credit risk"* → semantic search across all backends
- *"Customer segmentation analysis"* → generates customer LTV/churn report

### Report Status — Kanban Pipeline Board

Every report request becomes a card that moves through 8 pipeline columns in real-time:

| Column | What happens |
|--------|-------------|
| **To Do** | Report request received |
| **Interpreting** | Qwen parses NL query → domain, metrics, dimensions |
| **Fetching Data** | SQL query built and executed on ClickHouse Cloud |
| **Generating** | Qwen generates structured report with sections |
| **Charts** | SVG charts rendered (bar, line, pie) from data |
| **Compliance** | Data governance rules validated (PII, accuracy, methodology) |
| **Review** | Human-in-the-loop approval (approve / revise / reject) |
| **Published** | Report tracked in ClickHouse + indexed in Neo4j |

Cards update in real-time via Server-Sent Events as each pipeline step completes.

### Reports — Semantic Auto-Filing

Published reports are automatically categorized into folders using **Qwen `text-embedding-v3`** via Alibaba Cloud DashScope (1024-dim). The semantic router matches report content against folder descriptions:

- *Loan Portfolio Report* → `Loan Reports / Portfolio Analysis` (score: 0.83)
- *NPL Ratio Monitoring* → `Loan Reports / NPL Monitoring` (score: 0.81)
- *Transaction Volume by Channel* → `Transaction Reports / By Channel` (score: 0.78)
- *Branch Performance Comparison* → `Branch Performance` (score: 0.83)

### Data Sources — Live Infrastructure

Connected data sources visible in the sidebar:

| Source | Type | Status |
|--------|------|--------|
| `dwh.fact_loans` | ClickHouse | Active (640 rows) |
| `dwh.fact_deposits` | ClickHouse | Active (640 rows) |
| `dwh.fact_transactions` | ClickHouse | Active (640 rows) |
| `sb5.report.requests` | Redpanda (Kafka) | Active |
| `sb5.report.events` | Redpanda (Kafka) | Active |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│  React 19 + Vite + Jotai + TanStack Query                   │
│  SSE subscription → real-time updates                        │
│  Agent Panel / Kanban Board / TreeFile / Data Sources         │
└──────────────┬──────────────────────────────────────────────┘
               │ POST /api/iris/action
               │ GET  /api/iris/events (SSE)
┌──────────────┴──────────────────────────────────────────────┐
│                    Tachikoma Backend                          │
│                                                              │
│  Global Hive (polymorphic switch)                            │
│  ├── init / reset         (session management)               │
│  ├── chat → intent detect → search | report WOT              │
│  ├── kanban               (CRUD + pipeline sync)             │
│  ├── search               (Neo4j + ClickHouse + Graphiti)    │
│  ├── review               (HITL cast point)                  │
│  └── treefile / dashboard / history                          │
│                                                              │
│  Report WOT Pipeline (7 AgentEntity steps)                   │
│  Each agent has a SKILL.md + @tool methods on StatefulRecord │
│                                                              │
│  ReportRequest StatefulRecord                                │
│  ├── States: interpret → fetch → generate → charts →         │
│  │           compliance → review → publish → completed       │
│  ├── Tools: save_interpretation, fetch_warehouse_data,       │
│  │          save_report, render_report_charts,                │
│  │          run_compliance_check, approve, publish_report     │
│  └── Events: published to Redpanda on each step              │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────────────┐
│                    Infrastructure                            │
│                                                              │
│  Alibaba Cloud DashScope                                     │
│  ├── qwen3.6-plus (LLM — chat, report generation, entity    │
│  │                  extraction, compliance checking)          │
│  └── text-embedding-v3 (1024-dim embeddings for Graphiti)    │
│                                                              │
│  ClickHouse Cloud (Germany)                                  │
│  ├── dwh.fact_loans/deposits/transactions (3,360 rows)       │
│  ├── dwh.report_tracking (published reports)                 │
│  ├── dwh.kanban_cards/events (board state)                   │
│  ├── traces.spans (distributed tracing)                      │
│  └── monorepo_events (event bus persistence)                 │
│                                                              │
│  Neo4j Aura (Graph)                                          │
│  ├── ReportRequest → Department, ReportType relationships    │
│  ├── Chart → CONTAINS_CHART relationships                    │
│  └── Full-text search on query_text, report_type             │
│                                                              │
│  Graphiti (Semantic Knowledge Graph)                          │
│  ├── ZAILLMClient (retry-on-validation-error pattern)        │
│  ├── Alibaba embeddings (text-embedding-v3, 1024-dim)        │
│  └── Fact extraction: "Branch-C NPL ratio 7.1% Q4 2025"     │
│                                                              │
│  Redpanda Cloud (Singapore — Kafka-compatible)               │
│  ├── sb5.report.requests (pipeline input)                    │
│  ├── sb5.report.events (pipeline output + step events)       │
│  └── sb5.chart.pipeline (chart sub-pipeline)                 │
│                                                              │
│  Ray (Distributed compute)                                   │
│  ├── StatefulRecord actors (state_machine via Ray)            │
│  ├── HiveDeployer (serverless, scale-to-zero)                │
│  └── Dashboard on Tailnet                                    │
└──────────────────────────────────────────────────────────────┘
```

## How Qwen Powers IRIS

Qwen 3.6-Plus and Alibaba Cloud DashScope are used at **every layer** of the platform — not just for chat.

### Chat — Conversational Agent
The IRIS agent uses **Qwen 3.6-Plus** as its reasoning engine. When a user types a message, Qwen:
- Understands the intent (report generation vs search)
- Calls the right `@tool` methods on the `ReportRequest` StatefulRecord
- Generates human-readable responses in the user's language
- Handles multi-turn conversation with context from `ChatContextManager`

```
User: "Montre-moi le portefeuille de prêts par agence"
Qwen: calls save_interpretation(domain="loans", metrics="total_disbursed,outstanding_balance", ...)
Qwen: "I'll generate a loan portfolio report by branch. Interpreting your query..."
```

### Pipeline — 7 Agent Steps
Each pipeline step is an `AgentEntity` driven by **Qwen 3.6-Plus** with tool calling (`tool_choice: required`). The LLM doesn't just generate text — it calls Python tools:

| Step | Qwen does | Tool called |
|------|-----------|-------------|
| **Interpret** | Parses NL query → structured params | `save_interpretation(domain, metrics, dimensions)` |
| **Fetch** | Triggers data warehouse query | `fetch_warehouse_data()` |
| **Generate** | Creates structured report with sections | `save_report(title, summary, sections)` |
| **Charts** | Plans chart implementation | `render_report_charts()` |
| **Compliance** | Validates governance rules | `run_compliance_check()` |
| **Review** | Decides approve/revise/reject | `approve()` or `request_revision(notes)` |
| **Publish** | Finalizes and tracks | `publish_report()` |

### Kanban — Real-Time Status
As Qwen completes each pipeline step, SSE events push updates to the frontend. The Kanban card moves from column to column — the user sees the agent thinking and working in real-time.

```
[To Do] → [Interpreting] → [Fetching] → [Generating] → [Charts] → [Compliance] → [Review] → [Published]
    ↑         Qwen            SQL           Qwen          SVG         Rules          Qwen         Done
```

### Semantic Router — Auto-Filing Reports
After a report is published, **Qwen `text-embedding-v3`** (1024-dim, via DashScope) embeds the report content and matches it against folder descriptions using cosine similarity:

```python
report = "Loan Portfolio by Branch Q4 — NPL ratio analysis"
→ embed(report) via text-embedding-v3
→ cosine_similarity(report_vec, folder_vecs)
→ best match: "Loan Reports / Portfolio Analysis" (score: 0.83)
```

All 6 folder categories matched correctly in testing:

| Report | Filed to | Score |
|--------|----------|-------|
| Loan Portfolio by Branch | Loan Reports / Portfolio Analysis | 0.83 |
| NPL Ratio Monitoring | Loan Reports / NPL Monitoring | 0.81 |
| Transaction Volume | Transaction Reports / By Channel | 0.78 |
| Branch Performance | Branch Performance | 0.83 |
| Customer Segmentation | Customer Analytics | 0.80 |
| Deposit Growth | Deposit Reports | 0.78 |

### Search — Semantic Knowledge Graph (Graphiti)
When a user searches, **Qwen 3.6-Plus** powers Graphiti's entity extraction and fact retrieval:

1. **Indexing**: When a report is published, its content is sent to Graphiti. Qwen extracts entities and relationships (e.g., *"Branch-C has NPL ratio 7.1%"*) and `text-embedding-v3` generates the vector.

2. **Search**: The user's query is embedded with `text-embedding-v3`, then matched against stored facts via vector similarity + fulltext in Neo4j.

```
User: "Find reports about credit risk"
→ embed("credit risk") via text-embedding-v3
→ Graphiti search → Neo4j vector similarity
→ "Branch-C recorded an NPL ratio of 7.1% for Q4 2025" (fact extracted by Qwen)
→ "The loan portfolio reported an overall NPL ratio of 4.2%" (fact extracted by Qwen)
```

### Custom LLM Client — ZAILLMClient
Graphiti expects OpenAI's `responses.parse` API for structured output. DashScope supports the Responses API but doesn't enforce schema constraints. Our `ZAILLMClient` solves this with a **retry-on-validation-error** pattern:

1. Inject the Pydantic schema into the system prompt
2. Call `chat.completions` with `response_format: json_object`
3. Parse response with Pydantic model
4. If `ValidationError` → send the error back to Qwen → Qwen self-corrects → retry (max 2)

This makes Qwen 3.6-Plus work with any structured output schema without native schema enforcement.

### Summary: Qwen Everywhere

| Layer | Qwen Model | What it does |
|-------|-----------|-------------|
| **Chat** | qwen3.6-plus | Conversational agent, intent routing |
| **Pipeline (7 steps)** | qwen3.6-plus | Tool calling on StatefulRecord |
| **Report generation** | qwen3.6-plus | Structured report with sections + charts |
| **Chart elaboration** | qwen3.6-plus | Plans SVG chart implementation |
| **Compliance review** | qwen3.6-plus | Auto-approve/revise decision |
| **Semantic filing** | text-embedding-v3 | Report → folder matching (cosine similarity) |
| **Graphiti indexing** | qwen3.6-plus | Entity/fact extraction from reports |
| **Graphiti search** | text-embedding-v3 | Query embedding for semantic search |
| **Structured output** | qwen3.6-plus | JSON schema compliance (retry pattern) |

---

## Key Innovations

### 1. Skill-Driven Agents
Each pipeline step is an `AgentEntity` with a `SKILL.md` file that defines its behavior. The skill is loaded into the system prompt — no hardcoded prompts.

```
agent/
├── SKILL.md              ← Main skill: intent routing (report vs search)
├── report/
│   ├── SKILL.md          ← Report pipeline overview
│   ├── interpret/SKILL.md
│   ├── fetch/SKILL.md
│   ├── generate/SKILL.md
│   ├── charts/SKILL.md
│   ├── compliance/SKILL.md
│   ├── review/SKILL.md
│   └── publish/SKILL.md
└── search/
    └── SKILL.md          ← Multi-backend search
```

### 2. Graphiti + Qwen 3.6-Plus Integration
Graphiti (knowledge graph) uses Qwen 3.6-Plus for entity extraction and Alibaba's `text-embedding-v3` for semantic search. A custom `ZAILLMClient` handles the schema-in-prompt + retry-on-validation-error pattern for structured output compatibility.

### 3. StatefulRecord as Pipeline Entity
The `ReportRequest` is a Tachikoma `StatefulRecord` — a Faust Record with a state machine. Each pipeline step is a state, each `@tool` method is callable by the LLM agent. The state machine enforces transition conditions (e.g., can't generate without data, can't publish without compliance).

### 4. Semantic Auto-Filing
Published reports are automatically placed in the right folder using Qwen `text-embedding-v3` via Alibaba Cloud DashScope (1024-dim). The semantic router matches report content against folder descriptions with cosine similarity. 6/6 correct in testing.

### 5. Event-Driven Everything
Every action produces events:
- **ClickHouse**: traces, kanban events, report tracking
- **Redpanda**: pipeline step events (Kafka topics)
- **Neo4j**: entity graph (reports, charts, departments)
- **SSE**: real-time frontend updates

---

## Setup

```bash
# Clone
git clone https://github.com/HoliChrys/Iris-Qwen-Hackathon.git
cd Iris-Qwen-Hackathon

# Create .env from template
cp .env.example .env
# Fill in your credentials

# Backend
pip install faust-streaming openai kafka-python-ng
PYTHONPATH=. uvicorn backend.api:app --host 0.0.0.0 --port 8001

# Frontend
cd frontend && npm install && npm run dev

# Graphiti (optional — semantic search)
docker run -d --name graphiti -p 8002:8000 \
  -e NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io \
  -e OPENAI_API_KEY=$DASHSCOPE_API_KEY \
  -e OPENAI_BASE_URL=$DASHSCOPE_BASE_URL \
  -e MODEL_NAME=qwen3.6-plus \
  tachikoma-graphiti:retry
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | Alibaba Cloud Qwen 3.6-Plus (DashScope API) |
| **Embeddings** | Alibaba Qwen `text-embedding-v3` (1024-dim, DashScope) |
| **Framework** | Tachikoma (Faust + Ray + StatefulRecord) |
| **Frontend** | React 19, Vite 6, Jotai, TanStack Query, Tailwind CSS |
| **Data Warehouse** | ClickHouse Cloud (Germany) |
| **Graph Database** | Neo4j Aura |
| **Knowledge Graph** | Graphiti (semantic entity extraction) |
| **Message Broker** | Redpanda Cloud (Kafka-compatible, Singapore) |
| **Compute** | Ray (distributed, serverless) |
| **Tracing** | ClickHouse Cloud (custom CloudClickHouseTracer) |

## License

MIT
