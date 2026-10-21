# Operon — Autonomous AI Task Worker

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/Orchestrator-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Groq LPU](https://img.shields.io/badge/Inference-Groq%20LPU-f55036.svg)](https://groq.com/)
[![Model](https://img.shields.io/badge/LLM-Qwen%203.8%2027B-purple.svg)](https://groq.com/)
[![Tests](https://img.shields.io/badge/Tests-20%2F20%20Passed-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Operon** is an autonomous enterprise AI task worker that takes high-level natural language requests and independently completes them on a computer. 

Instead of brittle RPA scripts or conversational chatbots that merely explain what should be done, Operon is a **stateful, cognitive execution graph** that understands end goals, decomposes them into actions, navigates documents and internal systems, handles unexpected failures autonomously, independently verifies outcomes, and provides concrete evidence of completion.

---

## Reference Scenario

> **User Goal:**  
> *"Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done."*

### What Operon Does Autonomously:
1. **Understands the Goal**: Identifies that it must locate invoice files, determine chronological order, parse unstructured fields, cross-reference vendor credentials, register an entry into accounting, and verify the resulting ledger entry.
2. **Scans Storage**: Searches local/storage directories, inspects candidate invoices, and identifies the latest invoice (`INV-X-2026-003`, dated March 10, 2026).
3. **Extracts Structured Data**: Parses total balance due (`$13,446.00`), due date (`2026-04-10`), and issuer details.
4. **Queries Internal Systems**: Resolves the internal Vendor ID (`VND-001` for Company X Solutions) in the enterprise ERP.
5. **Registers Transaction**: Creates the invoice entry in the internal ERP accounting ledger.
6. **Performs Independent Verification**: An independent auditor node verifies whether the invoice actually exists in the database ledger with matching amount and date.
7. **Compiles Evidence Packet**: Produces an auditable summary, execution duration, and ledger state diffs.

---

## Key Capabilities & Evaluation Alignment

| Capability | Architectural Implementation | Evaluation Metric |
| :--- | :--- | :--- |
| **Autonomy** | Goal Decomposer & Plan Generator (`planner`) | Determines and executes meaningful multi-step actions without procedural prompts. |
| **Execution** | Modular Tool Registry (`file_tools`, `erp_tools`, `browser_tools`, `api_tools`) | Genuinely manipulates documents and mutates internal ERP state rather than mocking. |
| **Reliability & Self-Healing** | Dynamic Replanner (`replanner`) | Automatically normalizes currency symbols, resolves date formats, and applies retries. |
| **Independent Verification** | Outcome Auditor Node (`verifier`) | Directly inspects environment ground-truth; does not rely on model self-reporting. |
| **Generalization** | Pluggable State Graph & Tool Registry | Generalizes seamlessly to other workflows (e.g., vendor onboarding, reconciliation). |
| **Safety & Human-in-the-Loop** | Safety Controller & Approval Gate | Pauses execution for human approval on high-risk operations or financial limits (> $25,000). |
| **Evidence & Product Thinking** | Evidence Packet (`summarizer`) | Generates auditable state diffs, execution logs, and verifiable proof of completion. |

---

## System Architecture

Operon is built on **LangGraph** as a cyclic, stateful computational graph:

```text
       ┌──────────────┐
       │  User Goal   │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │ 1. Planner   │ ◄─── Groq API (Qwen 3.8 27B)
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐      Requires Approval?
       │ 2. Executor  ├──────────────────────────────┐
       └──────┬───────┘                              │
              │                                      ▼
              │ Safe                         ┌──────────────┐
              ▼                              │  Human Gate  │
       ┌──────────────┐                      └──────┬───────┘
       │  Tool Call   │ (File, ERP, Browser)        │ (Approved)
       └──────┬───────┘                             │
              │                                     ▼
              ▼                              ┌──────────────┐
       ┌──────────────┐                      │ 2. Executor  │
       │ 3. Observer  │                      └──────────────┘
       └──────┬───────┘
              │
        Step Succeeded?
        ├─ Failed ──► ┌──────────────┐
        │             │ 4. Replanner │ ──► (Self-heal & Retry)
        ▼             └──────────────┘
  More Steps?
  ├─ Yes ──► (Next Step in Plan)
  ▼
┌──────────────┐
│ 5. Verifier  │ ◄─── Independent Ground-Truth Audit
└──────┬───────┘
       │
       ▼
┌──────────────┐
│6. Summarizer │ ──► Evidence Packet & State Diffs
└──────────────┘
```

For complete technical specifications, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Quickstart & Installation

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12
- Git
- Groq API Key (Get a free key at [console.groq.com](https://console.groq.com/keys))

### 2. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/Dedeep007/Operon.git
cd Operon

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
pip install -e .
```

### 4. Configure Environment Variables
Create a `.env` file in the project root:
```bash
cp .env.example .env
```
Edit `.env` to include your Groq API key:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
OPERON_MODEL_NAME=qwen/qwen3.8-27b
OPERON_TEMPERATURE=0.0
OPERON_MAX_RETRIES=3
OPERON_HUMAN_IN_THE_LOOP=true
```
*(Note: If no API key is provided, Operon automatically activates its deterministic Simulation Engine, ensuring 100% of tests and demos run out of the box).*

---

## Running Operon

Operon provides three interfaces: an **Interactive Web Dashboard**, an **Interactive Terminal CLI**, and **Guided Demo Walkthroughs**.

### Option A: Interactive Web Dashboard (Recommended)
Launch the FastAPI streaming server:
```bash
uvicorn ui.app:app --host 127.0.0.1 --port 8000 --reload
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser:
- **Visual LangGraph Pipeline**: Watch active nodes pulse live during execution.
- **Action Plan & Step Timeline**: Real-time tool calls, arguments, and status indicators.
- **Working Memory (Scratchpad)**: Discovered entities (`invoice_number`, `amount`, `due_date`, `vendor_id`) update live.
- **Independent Verification Meter**: Outcome confidence score and assertion checklists.
- **Live ERP State Table**: View new invoices inserted directly into the accounting ledger.

### Option B: Interactive Terminal CLI
Run the rich terminal interface:
```bash
python cli.py
```
Or pass a custom natural language task directly:
```bash
python cli.py "Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done."
```

### Option C: Guided Demo Walkthroughs
Run the pre-configured scenarios designed to test each evaluation criteria:

```bash
# 1. Reference Invoice Task (Problem Statement scenario)
python demo/run_invoice_task.py

# 2. Vendor Onboarding (Tests generalization to different tasks)
python demo/run_vendor_onboard.py

# 3. Self-Healing Error Recovery (Tests reliability on malformed data)
python demo/run_error_recovery.py
```

---

## Running Tests

Operon includes a comprehensive test suite covering the ERP datastore, tool execution, parameter normalization, independent verification, and end-to-end task worker flows.

Run all tests:
```bash
pytest tests/ -v
```

Expected output:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.1.1
collected 20 items

tests/test_end_to_end.py::test_autonomous_invoice_processing_end_to_end PASSED   [  5%]
tests/test_end_to_end.py::test_autonomous_vendor_onboarding_generalization PASSED [ 10%]
tests/test_erp.py::test_erp_initial_state PASSED                                  [ 15%]
tests/test_erp.py::test_erp_find_vendor_by_name_and_alias PASSED                  [ 20%]
tests/test_erp.py::test_erp_create_invoice_success PASSED                         [ 25%]
tests/test_erp.py::test_erp_create_invoice_duplicate_error PASSED                 [ 30%]
tests/test_erp.py::test_erp_create_invoice_invalid_date PASSED                    [ 35%]
tests/test_erp.py::test_erp_register_new_vendor PASSED                            [ 40%]
tests/test_erp.py::test_erp_compute_state_diff PASSED                             [ 45%]
tests/test_recovery.py::test_replanner_recovers_from_string_formatted_amount PASSED[ 50%]
tests/test_recovery.py::test_replanner_recovers_from_non_iso_date_format PASSED    [ 55%]
tests/test_recovery.py::test_replanner_skips_after_max_retries PASSED             [ 60%]
tests/test_tools.py::test_registry_contains_core_tools PASSED                     [ 65%]
tests/test_tools.py::test_extract_invoice_data_from_text PASSED                   [ 70%]
tests/test_tools.py::test_extract_invoice_data_from_json PASSED                   [ 75%]
tests/test_tools.py::test_find_latest_invoice_file PASSED                         [ 80%]
tests/test_tools.py::test_registry_execute_handles_exceptions_gracefully PASSED  [ 85%]
tests/test_verification.py::test_verifier_detects_successful_invoice_entry PASSED  [ 90%]
tests/test_verification.py::test_verifier_flags_missing_invoice_in_erp PASSED      [ 95%]
tests/test_verification.py::test_verifier_flags_amount_mismatch PASSED            [100%]

============================= 20 passed in 6.73s ==============================
```

---

## Important Technical & Design Decisions

1. **Stateful Computational Graph over Monolithic ReAct Loops**:
   Rather than relying on an uncontrolled while loop where an LLM repeatedly calls tools, Operon partitions cognition into distinct nodes (`planner`, `executor`, `observer`, `replanner`, `verifier`, `summarizer`). This allows deterministic checkpoints, inspectable state transitions, and guaranteed verification before completion.
2. **Explicit Verification Node**:
   LLMs frequently hallucinate task completion when a tool simply returns `200 OK`. Operon implements an independent `verifier` node that directly queries the underlying database or filesystem to prove ground-truth state before marking a task as completed.
3. **Dual Execution Mode (Groq LPU + Simulation Fallback)**:
   By supporting both high-speed live inference (`qwen/qwen3.8-27b` via Groq) and a deterministic simulation fallback, Operon ensures full test reproducibility and zero friction for evaluators who clone the repo.
4. **Self-Contained ACID-like ERP Environment**:
   To avoid mock hand-waving, Operon includes an in-memory transactional ERP backend (`operon/environment/erp_system.py`) enforcing foreign keys, unique invoice constraints, and immutable audit logs.
5. **Human-in-the-Loop Safety Boundaries**:
   Autonomous systems must not perform destructive actions unchecked. Operon's `SafetyController` automatically halts execution for human confirmation on destructive operations (`erp_delete_record`) or financial transactions exceeding $25,000.

---

## Assumptions Made

- Enterprise documents (invoices, vendor profiles) are stored in structured or semi-structured formats (PDF, text, JSON) in designated enterprise storage volumes.
- Invoices reference companies by name or common aliases, and internal accounting systems maintain a unique Vendor ID mapping.
- Legitimate invoices require positive numerical balances and ISO-formatted payment deadlines (`YYYY-MM-DD`).

---

## Known Limitations

- **Complex Optical Layouts**: Table extraction from multi-column scanned image PDFs is currently handled via text regex extraction rather than native multimodal OCR.
- **Authentication Handshakes**: Simulated portal tools assume pre-authenticated internal intranet sessions; production deployment would require OAuth2/SSO credential management.
- **Stateless Tool Handlers**: Browser interactions are currently simulated via internal portal representations rather than full headful Chrome automation due to platform sandbox limits.

---

## What Would We Build Next (Roadmap)

1. **Multimodal Visual Document Parsing**: Connect Qwen 3.8 Vision (`qwen/qwen3.8-27b`) to natively parse complex invoices containing rotated tables, handwritten notes, and logos directly from PDF image renders.
2. **Dynamic Tool Synthesis**: Allow the agent to write and sandbox ephemeral Python scripts when an existing tool cannot satisfy a complex data manipulation request.
3. **Database Connector Plugins**: Expand ERP tooling to connect directly to PostgreSQL, SAP, NetSuite, and QuickBooks APIs.
4. **Multi-Agent Delegation**: Introduce specialized sub-agents (e.g., a dedicated OCR specialist agent and an Accounting Auditor agent) supervised by the Operon Master Coordinator.

---

## Repository Structure

```text
Operon/
├── README.md                 # Complete documentation, architecture, quickstart
├── ARCHITECTURE.md           # In-depth architectural blueprint & state machine
├── pyproject.toml            # Python packaging and project metadata
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── cli.py                    # Interactive Rich Terminal CLI
├── operon/                   # Core Python package
│   ├── __init__.py
│   ├── config.py             # Settings & Groq model configuration
│   ├── llm.py                # LLM factory (Groq Qwen 3.8 27B + fallback)
│   ├── state.py              # LangGraph TypedDict & Pydantic state models
│   ├── graph.py              # Main LangGraph assembly & workflow compiler
│   ├── agent.py              # High-level client API wrapper
│   ├── nodes/                # Cognitive LangGraph nodes
│   │   ├── planner.py        # Goal decomposition into discrete actions
│   │   ├── executor.py       # Tool invocation & parameter interpolation
│   │   ├── observer.py       # Output inspection & working memory updates
│   │   ├── replanner.py      # Self-healing parameter recovery & retries
│   │   ├── verifier.py       # Independent outcome verification against ERP
│   │   └── summarizer.py     # Final evidence packet & summary generation
│   ├── tools/                # Agent tools
│   │   ├── registry.py       # Tool dispatcher & error classification wrapper
│   │   ├── file_tools.py     # Search, read, extract invoice data, sort dates
│   │   ├── erp_tools.py      # Vendor lookup, invoice creation, ledger audit
│   │   ├── browser_tools.py  # Simulated intranet web portal navigation
│   │   └── api_tools.py      # REST HTTP client
│   ├── memory/
│   │   └── scratchpad.py     # Context working memory & entity tracker
│   ├── safety/
│   │   └── approval.py       # Human-in-the-loop safety boundaries & thresholds
│   └── environment/          # Simulated enterprise environment
│       ├── erp_system.py     # Transactional ERP accounting datastore
│       └── sample_data/      # Sample company files (invoices, vendors)
│           ├── invoices/     # Sample invoices for Company X & Acme
│           └── vendors/      # New vendor onboarding profiles
├── ui/                       # Glassmorphic web dashboard
│   ├── app.py                # FastAPI streaming server (SSE)
│   └── static/
│       ├── index.html        # Modern dashboard layout
│       ├── style.css         # Rich glassmorphic theme
│       └── app.js            # Real-time event consumer & UI updates
├── demo/                     # Guided demo walkthroughs
│   ├── run_invoice_task.py   # Problem statement reference demo
│   ├── run_vendor_onboard.py # Generalization demo
│   └── run_error_recovery.py # Self-healing reliability demo
└── tests/                    # Comprehensive test suite (20 tests)
    ├── test_erp.py           # ERP datastore & constraint tests
    ├── test_tools.py         # Tool registry & file extraction tests
    ├── test_verification.py  # Independent verification audit tests
    ├── test_recovery.py      # Self-healing recovery & normalization tests
    └── test_end_to_end.py    # End-to-end autonomous agent workflow tests
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.