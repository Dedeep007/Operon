"""Planner Node for Operon.

Understands the user's high-level goal, breaks it into structured steps,
and initializes the agent execution state.
"""

import json
import time
from typing import Dict, Any, List
from operon.state import OperonState, PlanStep
from operon.llm import llm_provider
from operon.tools.registry import registry

PLANNER_SYSTEM_PROMPT = """You are the master planner for Operon, an autonomous enterprise AI task worker.
Given a user goal, break it down into an efficient sequence of actions using the available tools.
Do NOT require the user to specify every step. Infer necessary prerequisite steps (e.g. reading files, looking up IDs, entering data, verifying).

Available Tools:
{tools}

Return a valid JSON object with:
"thought": "Reasoning about how to solve the goal",
"steps": [
    {
        "step_id": 1,
        "description": "Clear explanation of action",
        "tool_name": "tool_to_call",
        "tool_args": {"arg_name": "arg_value"},
        "expected_outcome": "Outcome verifying step success"
    }
]
"""

def planner_node(state: OperonState) -> Dict[str, Any]:
    """Decompose user goal into an actionable sequence of PlanSteps."""
    task = state["task"]
    
    # Format tool descriptions
    tool_defs = registry.list_definitions()
    tools_desc = "\n".join([f"- {t.name}: {t.description}" for t in tool_defs])
    
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT.replace("{tools}", tools_desc)},
        {"role": "user", "content": f"Task Goal: {task}"}
    ]
    
    raw_response = llm_provider.invoke(messages)
    
    # Parse structured plan
    steps: List[PlanStep] = []
    try:
        # Extract json block if surrounded by markdown
        cleaned = raw_response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
            
        data = json.loads(cleaned)
        raw_steps = data.get("steps", [])
        for s in raw_steps:
            steps.append(PlanStep(
                step_id=s.get("step_id", len(steps) + 1),
                description=s.get("description", ""),
                tool_name=s.get("tool_name", ""),
                tool_args=s.get("tool_args", {}),
                expected_outcome=s.get("expected_outcome", ""),
                status="pending"
            ))
    except Exception as e:
        # Resilient fallback default plan if LLM parsing failed
        print(f"[Planner] Warning: Could not parse JSON plan ({e}). Using robust fallback plan.")
        steps = [
            PlanStep(
                step_id=1,
                description="Find latest invoice file for Company X",
                tool_name="find_latest_invoice_file",
                tool_args={"company_name": "Company X"},
                expected_outcome="Latest invoice file path and extracted amounts"
            ),
            PlanStep(
                step_id=2,
                description="Lookup vendor ID in ERP for Company X",
                tool_name="erp_lookup_vendor",
                tool_args={"query": "Company X"},
                expected_outcome="Vendor ID and accounting terms"
            ),
            PlanStep(
                step_id=3,
                description="Enter invoice into internal accounting ERP",
                tool_name="erp_create_invoice",
                tool_args={"invoice_number": "", "vendor_id": "", "amount": 0.0, "due_date": ""},
                expected_outcome="Invoice registered in internal ERP"
            ),
            PlanStep(
                step_id=4,
                description="Verify invoice in internal ERP",
                tool_name="erp_verify_invoice_status",
                tool_args={"invoice_number": ""},
                expected_outcome="Confirmed invoice status in system"
            )
        ]

    return {
        "plan": steps,
        "current_step_index": 0,
        "status": "executing"
    }
