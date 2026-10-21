"""Interactive Command Line Interface for Operon Autonomous AI Task Worker."""

import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich import box

from operon.agent import OperonAgent
from operon.llm import llm_provider
from operon.config import settings

console = Console()

BANNER = """
[bold cyan]   ____                                [/bold cyan]
[bold cyan]  / __ \\____  ___  _________  ____     [/bold cyan]
[bold cyan] / / / / __ \\/ _ \\/ ___/ __ \\/ __ \\    [/bold cyan]
[bold cyan]/ /_/ / /_/ /  __/ /  / /_/ / / / /    [/bold cyan]
[bold cyan]\\____/ .___/\\___/_/   \\____/_/ /_/     [/bold cyan]
[bold cyan]    /_/                                [/bold cyan]
[bold yellow]Autonomous Enterprise Task Worker[/bold yellow]
"""

DEMO_TASKS = [
    "Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.",
    "Read the vendor profile for Apex Technologies and register them into our internal ERP.",
    "Process malformed invoice data with currency symbols to test self-healing parameter normalization."
]

def print_header():
    console.print(BANNER)
    info_table = Table(show_header=False, box=box.ROUNDED)
    info_table.add_column("Property", style="bold green")
    info_table.add_column("Value", style="white")
    
    info_table.add_row("LLM Architecture", f"Qwen 3.8 27B ({'Live Groq LPU' if llm_provider.is_live else 'Simulation Engine'})")
    info_table.add_row("Orchestrator", "LangGraph StateGraph with Checkpointing")
    info_table.add_row("Verification", "Independent Ground-Truth Ledger Auditor")
    info_table.add_row("Safety & HITL", "Enabled (High-Risk Thresholds & Approvals)")
    
    console.print(Panel(info_table, title="[bold]Agent Configuration[/bold]", border_style="cyan"))

def run_task(task_text: str):
    console.print(f"\n[bold green]Goal Received:[/bold green] [white]{task_text}[/white]\n")
    agent = OperonAgent()
    
    with console.status("[bold cyan]Operon is working autonomously...[/bold cyan]", spinner="dots"):
        events = list(agent.stream(task_text))
        
    for event in events:
        for node_name, node_state in event.items():
            if node_name == "planner":
                plan = node_state.get("plan", [])
                console.print(f"[bold magenta]Plan Generated ({len(plan)} steps):[/bold magenta]")
                plan_table = Table(box=box.SIMPLE)
                plan_table.add_column("#", style="cyan", width=4)
                plan_table.add_column("Action Description", style="white")
                plan_table.add_column("Tool", style="yellow")
                
                for s in plan:
                    plan_table.add_row(str(s.step_id), s.description, s.tool_name)
                console.print(plan_table)
                
            elif node_name == "executor":
                history = node_state.get("action_history", [])
                if history:
                    last_act = history[-1]
                    status_badge = "[bold green]OK[/bold green]" if last_act.success else "[bold red]FAIL[/bold red]"
                    console.print(f"[{status_badge}] [bold]Step {last_act.step_id}:[/bold] Calling tool [cyan]{last_act.tool_name}[/cyan] with args: [dim]{last_act.tool_args}[/dim]")
                    
            elif node_name == "replanner":
                errors = node_state.get("errors", [])
                if errors:
                    err = errors[-1]
                    console.print(f"[bold yellow]Self-Healing Replanner:[/bold yellow] Detected [red]{err.error_type}[/red]. Applying strategy: [green]{err.recovery_strategy}[/green]")
                    
            elif node_name == "verifier":
                verif = node_state.get("verification_result")
                if verif:
                    status_text = "[bold green]VERIFIED[/bold green]" if verif.is_verified else "[bold red]VERIFICATION FAILED[/bold red]"
                    console.print(f"\n[bold]Outcome Verification:[/bold] {status_text} (Score: {verif.confidence_score * 100:.0f}%)")
                    for c in verif.checks_performed:
                        console.print(f"  [green][PASS][/green] {c}")
                    console.print(f"  [bold]Evidence:[/bold] [dim]{verif.evidence}[/dim]")

            elif node_name == "summarizer":
                packet = node_state.get("evidence_packet")
                if packet:
                    console.print("\n" + "=" * 60)
                    console.print(Panel(
                        f"[bold green]TASK SUMMARY:[/bold green]\n{packet.summary}\n\n"
                        f"[bold cyan]Total Actions:[/bold cyan] {packet.total_actions_taken} | "
                        f"[bold cyan]Duration:[/bold cyan] {packet.execution_time_seconds}s | "
                        f"[bold cyan]Status:[/bold cyan] [bold]{packet.status.upper()}[/bold]\n\n"
                        f"[bold]State Changes Recorded:[/bold]\n{packet.state_diffs.get('total_new_invoices', 0)} new invoices in ERP ledger.",
                        title="[bold green]Final Evidence Packet[/bold green]",
                        border_style="green"
                    ))

def main():
    print_header()
    
    if len(sys.argv) > 1:
        task_input = " ".join(sys.argv[1:])
        run_task(task_input)
        return
        
    console.print("\n[bold]Choose an execution option:[/bold]")
    for i, demo in enumerate(DEMO_TASKS, 1):
        console.print(f"  [bold cyan]{i}.[/bold cyan] {demo}")
    console.print("  [bold cyan]4.[/bold cyan] Enter a custom natural language task")
    console.print("  [bold cyan]5.[/bold cyan] Exit\n")
    
    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default="1")
    
    if choice in ["1", "2", "3"]:
        run_task(DEMO_TASKS[int(choice) - 1])
    elif choice == "4":
        custom = Prompt.ask("\nEnter your natural language goal")
        if custom.strip():
            run_task(custom.strip())
    else:
        console.print("[dim]Goodbye![/dim]")

if __name__ == "__main__":
    main()
