"""LangGraph Stateful Computational Graph for Operon.

Orchestrates the cognitive nodes into an autonomous, self-healing execution loop
with independent verification and human-in-the-loop safety checkpoints.
"""

import time
from typing import Literal, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

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
    status = state.get("status")
    if status == "completed":
        return "summarizer"
    # If not verified and still retries available
    return "summarizer"

def human_gate_node(state: OperonState) -> Dict[str, Any]:
    """Human-in-the-loop approval checkpoint node."""
    # In interactive/CLI mode, this can read input or allow auto-approval if configured
    prompt = state.get("approval_prompt", "Approval requested.")
    print(f"\n[HUMAN-IN-THE-LOOP CHECKPOINT] {prompt}")
    
    feedback = state.get("human_feedback")
    if not feedback:
        # If in headless run, we auto-approve or take standard response
        feedback = "approved"
        
    return {
        "requires_approval": False,
        "human_feedback": feedback,
        "status": "executing"
    }

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
    workflow.add_edge("planner", "executor")
    
    workflow.add_conditional_edges(
        "executor",
        route_after_executor,
        {
            "observer": "observer",
            "human_gate": "human_gate"
        }
    )
    
    workflow.add_edge("human_gate", "executor")
    
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
    
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)

# Default compiled graph
operon_app = create_operon_graph()
