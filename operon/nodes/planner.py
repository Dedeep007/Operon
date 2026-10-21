"""Generate and validate a bounded action plan before executing tools."""

import json
from operon.state import PlanStep, ErrorRecord
from operon.llm import llm_provider
from operon.tools.registry import registry
from operon.workflows import offline_plan, SUPPORTED_TOOLS

PLANNER_SYSTEM_PROMPT = """Plan a task in a small simulated company environment.
Supported goals: processing a source invoice and onboarding a vendor from a local profile.
Use source documents and vendor lookup before writes. Never invent invoice IDs, amounts,
dates, vendor IDs, tax IDs, or a successful result. Use {{invoice_number}}, {{amount}},
{{due_date}}, {{vendor_id}}, {{vendor_name}}, {{tax_id}}, {{payment_terms}} and
{{contact_email}} to refer to facts found by earlier tools. Always verify outcomes.
For unsupported tasks or missing information return {"steps": [], "error": "Explain what is needed"}.
Return JSON with a steps array, each with step_id, description, tool_name, tool_args,
and expected_outcome. Use at most 12 steps. Available tools:
"""


def planner_node(state):
    tools = "\n".join(f"{t.name}: {t.description}" for t in registry.list_definitions() if t.name in SUPPORTED_TOOLS)
    raw = llm_provider.invoke([{"role": "system", "content": PLANNER_SYSTEM_PROMPT + tools},
                               {"role": "user", "content": state["task"]}])
    backend = llm_provider.last_backend
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(cleaned)
        steps = [PlanStep.model_validate(s) for s in data.get("steps", [])]
        if len(steps) > 12 or any(s.tool_name not in SUPPORTED_TOOLS for s in steps):
            raise ValueError("Unsupported tool or oversized plan")
        if [s.step_id for s in steps] != list(range(1, len(steps) + 1)):
            raise ValueError("Steps must have consecutive IDs")
    except (ValueError, TypeError, AttributeError):
        data = offline_plan(state["task"])
        steps = [PlanStep.model_validate(s) for s in data["steps"]]
        backend = "offline (invalid model plan)"
    for s in steps:
        s.status, s.result, s.error = "pending", None, None
    errors = list(state.get("errors", []))
    if not steps:
        errors.append(ErrorRecord(step_id=0, error_type="ClarificationRequired",
            message=data.get("error") or "No supported plan could be generated. Clarify the task and try again."))
    return {"plan": steps, "errors": errors, "current_step_index": 0, "planner_backend": backend,
            "status": "executing" if steps else "verifying"}
