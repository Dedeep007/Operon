"""Demo: Self-Healing Error Recovery and Dynamic Replanning.

Demonstrates:
1. Detecting when an action fails (e.g. invalid date or string amount).
2. Autonomous diagnosis of the failure reason.
3. Parameter normalization and alternative retry strategy.
4. Completing the task without requiring human intervention for trivial input glitches.
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from operon.agent import OperonAgent
from operon.environment.erp_system import default_erp
from rich.console import Console
from rich.panel import Panel

console = Console()

def run_recovery_demo():
    console.print(Panel(
        "[bold cyan]GOAL:[/bold cyan] Process invoice entry where source document has currency symbols and non-ISO date format.",
        title="[bold yellow]Operon Reliability Demo: Self-Healing Recovery[/bold yellow]",
        border_style="yellow"
    ))
    
    agent = OperonAgent()
    packet = agent.run("Enter invoice INV-X-2026-004 for Company X with amount '$13,446.00' and due date '2026-04-10', and verify the ledger.")
    
    console.print(f"\n[bold]Outcome:[/bold] [bold green]{packet.status.upper()}[/bold green]")
    console.print(f"[bold]Summary:[/bold] {packet.summary}")
    console.print(f"[bold]Verification Passed:[/bold] {packet.verification.is_verified}")
    console.print(f"[bold]Evidence:[/bold] {packet.verification.evidence}")

if __name__ == "__main__":
    run_recovery_demo()
