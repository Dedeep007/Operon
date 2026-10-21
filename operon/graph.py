"""LangGraph Stateful Computational Graph for Operon.

Orchestrates the cognitive nodes into an autonomous, self-healing execution loop
with independent verification and human-in-the-loop safety checkpoints.
"""

from typing import Literal, Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import interrupt
from operon.safety.approval import action_fingerprint

from operon.state import OperonState
from operon.nodes.planner import planner_node
from operon.nodes.executor import executor_node
from operon.nodes.observer import observer_node
from operon.nodes.replanner import replanner_node
from operon.nodes.verifier import verifier_node
from operon.nodes.summarizer import summarizer_node

def route_after_executor(state: OperonState) -> Literal["observer", "human_gate"]:
    """Route depending on whether action requires human-in-the-loop approval."""
    if state.get("requires_approval", False):
        return "human_gate"
    return "observer"

def route_after_observer(state: OperonState) -> Literal["executor", "replanner", "verifier"]:
    """Route depending on step outcome and plan progress."""
    status = state.get("status")
    if status == "replanning":
        return "replanner"
    elif status == "verifying":
        return "verifier"
    return "executor"

def route_after_replanner(state: OperonState) -> Literal["executor", "human_gate", "verifier"]:
    """Route after self-healing recovery attempt."""
    if state.get("requires_approval", False):
        return "human_gate"
    if state.get("status") == "verifying":
        return "verifier"
    return "executor"

def route_after_verifier(state: OperonState) -> Literal["summarizer", "replanner"]:
    """Route after verification check."""
    return "summarizer"

def human_gate_node(state: OperonState) -> Dict[str, Any]:
    """Human-in-the-loop approval checkpoint node."""
    step = state["plan"][state["current_step_index"]]
    fingerprint = action_fingerprint(step.step_id, step.tool_name, step.tool_args)
    decision = interrupt({
        "approval_id": fingerprint,
        "prompt": state.get("approval_prompt", "Approval requested."),
        "step_id": step.step_id,
        "tool_name": step.tool_name,
        "tool_args": step.tool_args,
    })
    plan = list(state["plan"])
    if decision is not True:
        for remaining in plan[state["current_step_index"]:]:
            remaining.status = "skipped"
    return {
        "plan": plan,
        "requires_approval": False,
        "approved_action": fingerprint if decision is True else None,
        "approval_rejected": decision is not True,
        "status": "executing" if decision is True else "verifying"
    }


def route_after_gate(state):
    return "verifier" if state.get("approval_rejected") else "executor"

def create_operon_graph():
    """Build and compile the LangGraph state machine."""
    workflow = StateGraph(OperonState)
    
    # 1. Add Nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("observer", observer_node)
    workflow.add_node("replanner", replanner_node)
    workflow.add_node("human_gate", human_gate_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("summarizer", summarizer_node)
    
    # 2. Add Edges & Conditional Routing
    workflow.add_edge(START, "planner")
    workflow.add_conditional_edges("planner", lambda state: "executor" if state.get("plan") else "verifier")
    
    workflow.add_conditional_edges(
        "executor",
        route_after_executor,
        {
            "observer": "observer",
            "human_gate": "human_gate"
        }
    )
    
    workflow.add_conditional_edges("human_gate", route_after_gate)
    
    workflow.add_conditional_edges(
        "observer",
        route_after_observer,
        {
            "executor": "executor",
            "replanner": "replanner",
            "verifier": "verifier"
        }
    )
    
    workflow.add_conditional_edges(
        "replanner",
        route_after_replanner,
        {
            "executor": "executor",
            "human_gate": "human_gate",
            "verifier": "verifier"
        }
    )
    
    workflow.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "summarizer": "summarizer",
            "replanner": "replanner"
        }
    )
    
    workflow.add_edge("summarizer", END)
    
    serializer = JsonPlusSerializer(allowed_msgpack_modules=[
        ("operon.state", name) for name in ("PlanStep", "ActionRecord", "ErrorRecord", "VerificationResult", "EvidencePacket")
    ])
    checkpointer = MemorySaver(serde=serializer)
    return workflow.compile(checkpointer=checkpointer)

# Default compiled graph
operon_app = create_operon_graph()
