# Project review and implemented changes

Date: 21 October 2026. Scope: the supplied **Autonomous AI Task Worker** internship problem statement.

The goal was to improve a narrow working prototype: interpret a business goal, execute meaningful actions in a simulated company environment, recover from errors, request approval when needed, verify results, and return useful evidence. Invoice processing and vendor onboarding remain the demonstration workflows.

## Review findings

| Finding in the original project | Why it mattered | Implemented response |
| --- | --- | --- |
| The human gate automatically supplied `approved` | High-risk operations did not actually wait for a person | Real LangGraph interrupts, exact-action decisions, dashboard and CLI resume paths |
| SSE converted the entire agent stream to a list | Users saw progress only after all work finished | Persist each node event as it occurs and stream it incrementally |
| Several plans and tools defaulted to Company X fields | Different goals could execute the wrong business operation | Data-driven offline plans, resolved placeholders, required source fields |
| Summary text invented Company X invoice details even for vendor tasks | The report could misrepresent what happened | Summaries generated from actual verification and records |
| State differences compared with the initial application seed | A later report could include records created by an earlier task | Snapshot the ERP at the start of every run |
| Generic verification treated a nonempty action history as success | Failed or irrelevant actions could be reported as completion | Explicit supported outcome checks and fail-closed verification |
| Source expectations could be replaced by write-tool output | The auditor could compare a wrong record against the same wrong output | Preserve invoice/profile source data separately from mutable entities |
| Currency cleanup discarded negative signs; date checks accepted impossible dates | Invalid values could enter the ledger or evade policy interpretation | Shared strict monetary parsing and real calendar validation |
| Invoice selection used broad tokens and preferred filename matches | Company X could match Company Y; a newer content match could be ignored | Match source issuer identity and compare all matching document dates |
| API failures could turn into simulated HTTP 200 responses | A failed request could look successful | Preserve request failures and reject unsuccessful HTTP status codes |
| A deletion helper returned success without deleting anything | A tool advertised work it did not perform | Return an explicit unsupported-operation error; exclude it from planning |
| The UI emphasized engine branding, glowing nodes, badges, and dense panels | Users had to interpret implementation details to find the result | A calmer task workspace organized around work and evidence |

## Implemented behavior

### 1. Source-driven workflow generalization

- Company X, Acme, Globex, and OmniCorp use the same invoice workflow: find the latest source, resolve the vendor, enter the invoice, and check the record.
- Apex, Quantum, Horizon, and Cyberdyne use the same onboarding workflow: read the source profile, register it, and verify its fields and active status.
- The offline planner reads only the user's task when choosing a scenario. Tool descriptions in the system prompt no longer accidentally trigger vendor onboarding.
- Invalid model plans fall back to a bounded plan for the requested task. Unsupported goals produce a clarification explanation.
- Missing invoice IDs, tax IDs, vendor IDs, amounts, and dates are no longer replaced with invented business data.
- The simulated ERP enforces source invoice identity, positive finite monetary values, calendar dates, and vendor conflicts.
- Matching repeated entries are idempotent. Conflicting records remain visible as errors.

### 2. Genuine approval and bounded recovery

- Financial entries above $25,000 pause when approval checks are enabled, including formatted values such as `$48,500.00`.
- Approval is bound to the resolved step/tool/arguments fingerprint and consumed by that action.
- Declining prevents that action and stops dependent work. Duplicate or stale HTTP decisions are rejected.
- The CLI streams events as they happen and asks for a decision at the same checkpoint. A noninteractive EOF declines.
- Recovery uses validated transformations and facts already discovered. It no longer substitutes vendor `VND-001` after a failed lookup.
- Retry exhaustion and permanent conflicts stop downstream work before verification.
- The recovery demo now creates a temporary malformed invoice that actually fails ERP validation, gets repaired, retries, and passes the independent audit.

### 3. Preview changes

This extension makes autonomous execution reviewable. The same agent graph runs against an independent copy of the current ERP and produces a report of proposed records and balances.

- The shared ledger and its audit log are unchanged by preview execution.
- The report labels the mode as `preview` and records actions that would need approval during execution.
- Non-sandbox tools such as file writes and arbitrary API calls are blocked in the preview dispatcher.
- Preview does not automatically commit anything. Running the goal afterward creates a new execution against the current company ledger.
- The isolation applies to ERP writes; this is not a general-purpose operating-system sandbox.

### 4. Independent verification and evidence

- Source snapshots are retained separately from tool write responses.
- Verification checks document integrity, invoice presence, amount, due date, and vendor identity; onboarding checks the actual profile fields.
- An existing invoice under the wrong vendor fails verification even if its amount and date match.
- A source file changed during execution fails the integrity check.
- Agent runs without a captured invoice source cannot claim a source-verified invoice outcome.
- Reports count only the records created during that run, including new vendors and balance changes.
- A failure after an earlier successful write is reported as partial completion.
- Downloadable JSON includes source hashes, typed plans, action history, errors, recovery, policy checks, planner backend, and a SHA-256 report digest.
- The digest supports comparison with a retained original. It is not a signed or tamper-proof audit system.

### 5. Saved history and real progress

- `POST /api/runs` starts work once; the event endpoint only observes it.
- SQLite persists node events immediately, alongside task metadata and completed reports.
- SSE reconnects use event IDs and replay saved events instead of re-executing the task.
- The dashboard has one active task, so ledger changes and resets cannot race across dashboard runs.
- Restarting preserves reports, marks unfinished work interrupted, and explains that its in-memory checkpoint cannot resume.
- The ERP itself remains in memory. This limitation is explicit in the UI documentation and architecture.

## UI review and redesign

The intended feel is a small operations product, with clear typography and restrained visual treatment.

| Previous treatment | Current treatment |
| --- | --- |
| Dark glass panels and repeated badges | Neutral paper background, simple borders, and a single restrained accent |
| Giant model and framework labels | Task title, business scope, and a compact planner label in the footer |
| Animated cognitive pipeline as the main visual | A readable plan and activity list with progress states |
| Dense task preset chips | One example selector |
| Technical arguments always visible | Expandable action details |
| Working-memory object dump | Collected business facts and source documents |
| A numeric confidence meter without clear context | A verification outcome, performed checks, evidence, and discrepancy explanation |
| Always-successful completion banner | Separate completed, partial, failed, interrupted, and preview states |
| No decision workflow | An explicit approval panel showing the resolved arguments |
| No task history or downloadable evidence | Recent-task replay and an evidence download |
| External web font dependencies | System fonts; no frontend build step |

Additional details:

- A separate preview action explains that its ledger is isolated.
- The company ledger and vendor directory remain inspectable after execution.
- Dynamic text is inserted using DOM text nodes to avoid interpreting source content as HTML.
- Controls include labels, focus states, live status text, and disabled states during work.
- Narrow layouts stack the panels and expose history through the Recent tasks toggle.

## Files changed

| Area | Files |
| --- | --- |
| Agent lifecycle and graph | `operon/agent.py`, `operon/graph.py`, `operon/state.py` |
| Model and offline planning | `operon/llm.py`, `operon/workflows.py`, `operon/config.py`, `.env.example` |
| Execution, recovery, and audit | `operon/nodes/planner.py`, `executor.py`, `observer.py`, `replanner.py`, `verifier.py`, `summarizer.py` |
| Policy and source memory | `operon/safety/approval.py`, `operon/memory/scratchpad.py`, `operon/validation.py` |
| ERP and environment binding | `operon/environment/erp_system.py`, `operon/environment/context.py` |
| Tool correctness | `operon/tools/file_tools.py`, `erp_tools.py`, `api_tools.py` |
| Saved execution | `operon/runs.py`, `ui/app.py` |
| UI | `ui/static/index.html`, `style.css`, `app.js` |
| CLI and recovery demo | `cli.py`, `demo/run_error_recovery.py` |
| Packaging | `pyproject.toml`, `requirements.txt`, `operon/__init__.py`, `.gitignore` |
| Regression coverage | `tests/conftest.py`, `test_workflows.py`, `test_dashboard.py`, `test_source_integrity.py` |
| Documentation | `README.md`, `ARCHITECTURE.md`, this file |
| Browser screenshots | `docs/ui-workspace.png`, `docs/ui-preview.png`, `docs/ui-approval.png` |

Packaging now includes the CLI module and sample data. HTTPX is declared for dashboard tests. Local SQLite reports are ignored by Git. The example configuration explains explicit offline versus optional Groq planning.

## Alignment with evaluation criteria

| Criterion | Demonstrable improvement |
| --- | --- |
| Autonomy | A goal generates prerequisite steps and passes discovered facts between them |
| Execution | Files are read and the simulated ERP is actually mutated |
| Reliability | A genuine failure/retry demo, strict validation, idempotence, bounded retries, and stopped dependencies |
| Verification | Ground-truth checks against preserved source data and ledger state |
| Generalization | One graph handles multiple companies and both invoice and onboarding tasks |
| Engineering quality | Typed plans, restricted tools, isolated previews, per-run snapshots, persistent event history, and regression tests |
| Product thinking | Clear outcomes, understandable approval requests, inspectable changes, and evidence export |
| Technical understanding | Architecture, explicit tradeoffs, known limits, and runnable demos |

The extensions that distinguish this prototype are the **same-graph ERP preview**, **source-linked verification**, and **replayable evidence history**. Their purpose is to make the worker's actions and claims inspectable.

## Validation

- Original baseline: 20 tests passed before changes.
- Expanded suite: 64 tests passed using `python -m pytest tests -q`.
- Test fixtures force the offline planner and reset ERP state between tests.
- Coverage includes both workflows, all sample companies, approvals and declines, exact-action approval scope, preview isolation, blocked preview file writes, duplicate handling, source modifications, wrong-vendor writes, bad amounts/dates, report digest changes, API input validation, saved SSE replay, early event visibility, and restart handling.
- `node --check ui/static/app.js` passed.
- The real recovery demo completed after a failed validation attempt and successful retry.
- Browser inspection confirmed the redesigned layout, a completed preview with the company ledger unchanged, a real OmniCorp approval pause, a declined action with no invoice created, saved history replay, and the narrow-screen history toggle.
- The Python wheel built successfully with `pip wheel . --no-deps --wheel-dir storage/package-check`; its contents include the CLI module and sample invoice/vendor data.
### 6. Live LLM Agent on Simulation Dummy Data

- **Active Groq Reasoning in Sandbox**: Removed artificial offline constraints (`settings.environment != "simulation"`) so that whenever a `GROQ_API_KEY` is provided, the live Groq model (`qwen/qwen3.8-27b`) acts as the primary cognitive engine across all simulated files, mock ERP records, and intranet tools.
- **Universal Tool Support**: Expanded `SUPPORTED_TOOLS` to include all registered tools (`search_files`, `read_document`, `write_file`, `erp_*`, `browser_*`, `api_request`).
- **Generalized Dynamic Planning**: Updated `PLANNER_SYSTEM_PROMPT` to allow the LLM to autonomously deconstruct arbitrary natural-language requests into grounded steps.
- **Resilient Argument Normalization**: Handled schema variations (`tool_args`, `args`, `input`, `tool`, `tool_name`, `output_ref`, dotted placeholders like `{{invoice_data.amount}}`) in the scratchpad working memory.
- **Extended Simulation Data**: Added dummy architectural blueprints, invoices, documents, and vendor profiles for Balaji Construction and Titan Industrial to allow exploratory searches and verifications.
- **Guaranteed Test Offline Isolation**: Maintained complete offline determinism for test fixtures; all 64 pytest test cases pass cleanly without external network calls.

### Screenshots from the running prototype

The task desk:

![Redesigned Operon task desk](docs/ui-workspace.png)

A preview report alongside the unchanged company ledger:

![Verified preview and unchanged ledger](docs/ui-preview.png)

A high-value action paused before execution:

![OmniCorp approval checkpoint](docs/ui-approval.png)

## Suggested next improvements

1. **Durable ERP plus durable checkpoints.** Persist both together so a paused task can safely resume after a restart. A report database alone is insufficient.
2. **A small held-out evaluation set.** Use unfamiliar synthetic vendors, missing fields, duplicate conflicts, changed sources, and transient failures. Report completion and false-success rates for offline and live planners separately.
3. **Conversational clarification.** Let a user supply a missing company or correct one ambiguous field while retaining the current plan and evidence.
4. **One real sandbox connector.** If needed, replace the ERP adapter with a permitted test API while preserving policy and verification. Add it only after the local demo remains reliable.

Scanned-document OCR, arbitrary desktop control, payment execution, multi-agent delegation, and multiple enterprise integrations remain outside this implementation. They would expand the prototype beyond the supplied brief's preference for narrow, genuine functionality.
