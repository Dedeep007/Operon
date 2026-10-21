# Operon

An autonomous task worker for a small simulated company environment. Give it an end goal, and it finds source information, plans tool calls, updates a working ERP ledger, and checks the result against the source.

> Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.

The prototype focuses on two workflows: **latest-invoice processing** and **vendor onboarding**. It uses real local files and an in-memory ERP with validation, balances, and audit records. The same graph handles both workflows.

See [CHANGES.md](CHANGES.md) for the project review, UI redesign, implemented improvements, validation, and proposed next steps. [ARCHITECTURE.md](ARCHITECTURE.md) explains the implementation.

## Setup

Python 3.10+ is required. From the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
Copy-Item .env.example .env
```

On macOS/Linux, activate with `source .venv/bin/activate` and copy the configuration with `cp .env.example .env`.

The default `.env.example` selects `OPERON_ENVIRONMENT=simulation`. This uses a deterministic, data-driven planner and needs no credentials or external service. It is an offline demonstration of the execution graph; model-based reasoning is optional.

For Groq planning, explicitly set:

```env
OPERON_ENVIRONMENT=auto
GROQ_API_KEY=your_groq_api_key_here
OPERON_MODEL_NAME=qwen/qwen3.8-27b
OPERON_TEMPERATURE=0.0
OPERON_MAX_RETRIES=3
OPERON_HUMAN_IN_THE_LOOP=true
```

Keep credentials in `.env`, which Git ignores. Use synthetic company data. The configured model is listed in [Groq's supported models](https://console.groq.com/docs/models); model availability can change. A failed model request falls back to the offline planner, and the evidence report identifies that fallback.

## Run

Launch the dashboard:

```powershell
uvicorn ui.app:app --host 127.0.0.1 --port 8000
```

Open [localhost:8000](http://localhost:8000). Windows users can also run `run_dashboard.bat`.

- **Run task** executes against the company ERP.
- **Preview changes** runs the same workflow against an independent ledger copy. Proposed records, balance changes, verification, and approval requirements appear in its report.
- High-value entries over $25,000 pause for an **Approve this action** or **Decline & stop** decision when approval checks are enabled.
- Recent tasks replay saved activity. **Download evidence** exports the source hashes, tool calls, verification, changes, errors, and report digest.
- **Reset sandbox** restores seeded ERP records. It is blocked while a task is running or waiting for approval.

Run the CLI:

```powershell
python cli.py
python cli.py "Find the latest invoice from Globex Software and register it in ERP, then verify."
python cli.py --preview --output storage/evidence.json "Find the latest invoice from OmniCorp and enter it into ERP, then verify."
```

The installed `operon` command uses the same CLI. It streams progress and prompts for approval before a gated action. Preview bypasses the approval pause inside its isolated copy and records the policy requirement.

## Supported examples

| Goal | Source / outcome |
| --- | --- |
| Latest Company X invoice | `INV-X-2026-003`, $13,446.00, due 2026-04-10 |
| Latest Acme Logistics invoice | `INV-ACM-2026-002`, $14,280.50, due 2026-04-15 |
| Latest Globex Software invoice | `INV-GLX-2026-002`, $6,850.00, due 2026-04-30 |
| Latest OmniCorp invoice | `INV-OMNI-2026-001`, $48,500.00, approval required |
| Onboard Apex, Quantum, Horizon, or Cyberdyne | Read the corresponding JSON profile and verify the registered name, tax ID, payment terms, email, and active status |

Repeating an invoice or vendor task with identical data verifies the existing record without duplicating it. Conflicting existing details produce a failure requiring attention.

Unsupported offline tasks return an actionable explanation. Operon does not substitute an unrelated Company X task or invent missing invoice fields.

## Architecture and decisions

```text
Goal → Planner → Executor → Observer → Verifier → Evidence
                   ↑          │
                   └ Replanner┘
                   ↕
              Approval checkpoint
```

The planner generates a validated list of tool calls. The executor resolves values discovered by earlier steps, evaluates approval policy, and runs each tool. The observer stores facts and detects failures. Recovery is bounded; a permanent failure stops dependent actions. The verifier independently reads the ERP and compares it with the captured source fields and document hashes.

LangGraph separates these responsibilities and checkpoints approval pauses. A single dashboard worker keeps shared ledger changes attributable to one run. SQLite stores reports and incremental events; reconnecting a stream reads those events instead of submitting the task again.

Reports use the ledger snapshot taken at the start of that run, so earlier tasks cannot inflate their record counts. A SHA-256 digest makes a downloaded report comparable with a retained copy; it is an integrity checksum, not a digital signature.

## Test and demonstrate

```powershell
python -m pytest tests -q
python demo/run_invoice_task.py
python demo/run_vendor_onboard.py
python demo/run_error_recovery.py
```

The suite has 64 passing tests covering the original workflows, independent verification, source selection, recovery, approval scope, preview isolation, duplicate handling, API validation, saved-event replay, and restart handling. Tests force offline planning and reset shared fixtures; they never call Groq.

The recovery demo creates a temporary malformed JSON invoice. Its prose-formatted date fails ERP validation, is normalized, retries successfully, and is checked against the source. The original sample files are unchanged.

A short demo recording can follow this sequence:

1. Preview Company X and show that the company ledger remains unchanged.
2. Run Company X, inspect the ledger entry, and download its evidence.
3. Select OmniCorp and show the approval pause before an entry is created; decline it or explicitly approve the simulated action.
4. Onboard Quantum to demonstrate the same graph handling a different goal.
5. Run the recovery demo in the terminal and show the failed attempt followed by a successful retry.

## Assumptions and limits

- The demonstration uses synthetic USD invoices and known local vendor profiles. Text/JSON extraction is deterministic; scanned PDF OCR and complex layouts are outside the supported demo.
- The ERP is in memory and resets when the server restarts. SQLite run reports and events persist under `storage/runs.sqlite3`.
- Approval checkpoints live in the current process. A restart marks unfinished runs as interrupted and clears their pending decisions. Review the ledger before starting another task; automatic restart recovery is a future improvement.
- One task runs at a time in the dashboard. Separate CLI processes use separate in-memory ERP instances.
- The local dashboard has no authentication and is intended to bind to localhost. Multi-user hosting, external accounting connectors, payments, and unrestricted desktop automation are outside this prototype.
- The offline planner recognizes the bounded workflows and known companies; the optional Groq planner provides model-based decomposition over the same restricted tool set. Live Groq calls were not part of the automated validation.
- Legacy simulated browser helpers are excluded from the planner's supported tools. Their existence is not evidence of real browser automation.
- A failed task can leave earlier successful entries in the ERP. The report identifies partial completion; the worker does not silently roll back business records.

## Components

Python, LangGraph and its in-memory checkpointer, Pydantic, FastAPI, Uvicorn, SQLite from the standard library, Rich for the CLI, pytest/HTTPX for testing, pypdf for basic PDF text extraction, and an optional Groq model through `langchain-groq`. The dashboard uses plain HTML, CSS, and JavaScript with system fonts and no frontend build step.

Next priorities are a durable ERP/checkpointer pair, an evaluation set of unfamiliar synthetic tasks and failure cases, and conversational clarification that can revise a paused plan. See the rationale in [CHANGES.md](CHANGES.md).

MIT license. See [LICENSE](LICENSE).
