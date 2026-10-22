"""Generate and validate a bounded action plan before executing tools."""

import json
from operon.state import PlanStep, ErrorRecord
from operon.llm import llm_provider
from operon.tools.registry import registry
from operon.workflows import offline_plan, SUPPORTED_TOOLS

PLANNER_SYSTEM_PROMPT = """You are Operon, an autonomous AI task worker operating in a company sandbox with dummy data, documents, vendor profiles, blueprints, internal portals, and an ERP ledger.

Deconstruct the user's natural language goal into a sequence of concrete, bounded tool actions.
Common task patterns:
1. Invoice processing: Locate source file (find_latest_invoice_file or search_files), lookup vendor in ERP (erp_lookup_vendor), enter invoice record (erp_create_invoice), and verify status (erp_verify_invoice_status).
2. Vendor onboarding: Read vendor profile (read_vendor_profile or read_document), then register in ERP (erp_register_vendor).
3. Finding or inspecting documents/blueprints/files: Search storage (search_files), then inspect content (read_document).
4. ERP queries/audits: Use erp_lookup_vendor, erp_get_invoice, or erp_list_invoices.
5. Intranet portals: Use browser_navigate, browser_fill_form, browser_get_dom.
6. API tasks: Use api_request.
7. Deal quotations: Find the latest signed deal with find_latest_signed_deal (optional customer), then read_deal_quotation using {{deal_id}}. Do not guess which deal is latest or substitute another quotation for a missing link.
8. Cross-source discovery: search_company_records searches local document contents, invoices, and vendors together with a query.

Guidelines:
- Ground all actions in facts. Never invent invoice IDs, amounts, dates, or vendor IDs when they can be extracted from source documents or lookups.
- Missing resources are valid outcomes. Use actual lookup results and never invent a document or declare success after an empty search. Ask for clarification when several sources could fit.
- Dynamic references: Use {{invoice_number}}, {{amount}}, {{due_date}}, {{vendor_id}}, {{vendor_name}}, {{tax_id}}, {{payment_terms}}, {{contact_email}}, {{file_path}} to reference facts discovered by earlier steps.
- Always generate an exploratory plan for search, investigation, or inspection tasks rather than returning an empty plan. Only return {"steps": [], "error": "Reason"} if the task is completely incomprehensible or impossible.
- Maximum 12 steps.
- CRITICAL REQUIREMENT: Output strictly a single JSON object starting with { and ending with }. Never output any greeting, preamble, conversational text, or explanation before or after the JSON.

Available tools:
"""


def planner_node(state):
    tools = "\n".join(f"{t.name}: {t.description}" for t in registry.list_definitions() if t.name in SUPPORTED_TOOLS)
    raw = llm_provider.invoke([{"role": "system", "content": PLANNER_SYSTEM_PROMPT + tools},
                               {"role": "user", "content": state["task"]}])
    backend = llm_provider.last_backend
    try:
        cleaned = raw.strip()
        if "{" in cleaned and "}" in cleaned:
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1].strip()
        data = json.loads(cleaned)
        raw_steps = data.get("steps", [])
        steps = []
        for i, s in enumerate(raw_steps, 1):
            if not isinstance(s, dict):
                continue
            s["step_id"] = i
            tool_name = s.get("tool_name") or s.get("tool") or s.get("action") or s.get("name")
            s["tool_name"] = str(tool_name).strip() if tool_name else ""
            tool_args = (s.get("tool_args") or s.get("args") or s.get("parameters") or
                         s.get("arguments") or s.get("input") or {})
            if not isinstance(tool_args, dict):
                tool_args = {}
            if "description" in tool_args and not s.get("description"):
                s["description"] = tool_args.pop("description")
            s["tool_args"] = tool_args
            if not s.get("description"):
                s["description"] = s.get("desc") or f"Execute {s['tool_name']}"
            if not s.get("expected_outcome"):
                s["expected_outcome"] = s.get("expected_result") or s.get("outcome") or s["description"]
            steps.append(PlanStep.model_validate(s))
        if len(steps) > 12 or any(s.tool_name not in SUPPORTED_TOOLS for s in steps):
            raise ValueError("Unsupported tool or oversized plan")
        backend = llm_provider.last_backend
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        data = offline_plan(state["task"])
        steps = [PlanStep.model_validate(s) for s in data["steps"]]
        backend = f"offline ({llm_provider.last_backend})"
    for s in steps:
        s.status, s.result, s.error = "pending", None, None
    errors = list(state.get("errors", []))
    if not steps:
        errors.append(ErrorRecord(step_id=0, error_type=data.get("error_type", "ClarificationRequired"),
            message=data.get("error") if isinstance(data, dict) else "No supported plan could be generated. Clarify the task and try again."))
    return {"plan": steps, "errors": errors, "current_step_index": 0, "planner_backend": backend,
            "status": "executing" if steps else "verifying"}
