"""Terminal interface for the same task graph used by the dashboard."""

import argparse
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.markup import escape
from operon.agent import OperonAgent
from operon.llm import llm_provider

console = Console()
DEMO_TASKS = [
    "Find the latest invoice from Company X, enter it into our ERP, and verify the amount and due date.",
    "Read the vendor profile for Quantum Cloud Systems and register them into our ERP.",
    "Find the latest invoice from OmniCorp Industries, enter it into our ERP, and verify the result.",
]


def run_task(task_text, mode="execute"):
    console.print(Panel(escape(task_text), title="Preview" if mode == "preview" else "Task"))
    agent = OperonAgent(mode=mode)
    events = agent.stream(task_text)
    packet = None
    while True:
        for event in events:
            if "__interrupt__" in event:
                continue
            for node, data in event.items():
                if node == "planner":
                    console.print(f"Plan: {len(data.get('plan', []))} steps")
                    for step in data.get("plan", []):
                        console.print(f"  {step.step_id}. {escape(step.description)}")
                elif node == "executor" and data.get("action_history"):
                    action = data["action_history"][-1]
                    console.print(f"  {'OK' if action.success else 'FAILED'} · Step {action.step_id} · {escape(action.tool_name)}")
                elif node == "replanner":
                    for error in data.get("errors", []):
                        if error.recovery_strategy:
                            console.print(f"Recovery: {escape(error.recovery_strategy)}")
                elif node == "summarizer":
                    packet = data["evidence_packet"]
        approval = agent.pending_approval
        if not approval:
            break
        console.print(Panel(escape(approval["prompt"]) + "\n" + escape(json.dumps(approval["tool_args"], indent=2)), title="Approval required"))
        try:
            decision = Confirm.ask("Approve this action?", default=False)
        except (EOFError, KeyboardInterrupt):
            decision = False
        events = agent.resume_stream(decision)
    if packet:
        color = "green" if packet.status == "completed" else "yellow"
        console.print(Panel(escape(packet.summary), title=packet.status.replace("_", " ").title(), border_style=color))
        console.print(f"{packet.total_actions_taken} actions · {packet.execution_time_seconds}s · {len(packet.created_records)} new records")
        console.print(f"Evidence SHA-256: {packet.evidence_sha256}")
    return packet


def main():
    parser = argparse.ArgumentParser(description="Operon: a task worker for a simulated company ERP.")
    parser.add_argument("task", nargs="*", help="Natural language task")
    parser.add_argument("--preview", action="store_true", help="Execute against an isolated ERP copy")
    parser.add_argument("--output", type=Path, help="Save the JSON evidence report")
    args = parser.parse_args()
    console.print(f"Operon · {llm_provider.model_name} · Simulated ERP")
    task = " ".join(args.task)
    if not task:
        for index, example in enumerate(DEMO_TASKS, 1):
            console.print(f"{index}. {example}")
        console.print("4. Custom task\n5. Exit")
        choice = Prompt.ask("Select a task", choices=["1", "2", "3", "4", "5"], default="1")
        if choice == "5":
            return
        task = Prompt.ask("Task") if choice == "4" else DEMO_TASKS[int(choice) - 1]
    packet = run_task(task, "preview" if args.preview else "execute")
    if args.output and packet:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(packet.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"Saved evidence to {args.output.resolve()}")


if __name__ == "__main__":
    main()
