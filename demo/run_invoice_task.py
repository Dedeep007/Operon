"""Demo: Autonomous Invoice Processing (Problem Statement Reference Task).

Task:
"Find the latest invoice from Company X, extract the amount and due date,
enter it into our internal system, and tell me once it is done."
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from operon.agent import OperonAgent
from operon.environment.erp_system import default_erp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def run_invoice_demo():
    console.print(Panel(
        "[bold cyan]TASK:[/bold cyan] Find the latest invoice from Company X, extract the amount and due date,\n"
        "enter it into our internal system, and tell me once it is done.",
        title="[bold green]Operon Autonomous AI Worker Demo[/bold green]",
        border_style="cyan"
    ))
    
    agent = OperonAgent()
    console.print("\n[bold yellow]Agent executing autonomously...[/bold yellow]\n")
    
    packet = agent.run("Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.")
    
    # Display Action Audit Trail
    table = Table(title="Execution Audit Log")
    table.add_column("Step #", style="cyan", width=8)
    table.add_column("Tool", style="yellow")
    table.add_column("Success", style="green", width=10)
    table.add_column("Observation Summary", style="white")
    
    for act in packet.action_log:
        obs_summary = str(act.observation)
        if len(obs_summary) > 70:
            obs_summary = obs_summary[:67] + "..."
        table.add_row(
            str(act.step_id),
            act.tool_name,
            "[bold green]YES[/bold green]" if act.success else "[bold red]NO[/bold red]",
            obs_summary
        )
    console.print(table)
    
    # Verification & Ground Truth
    console.print("\n[bold green]Independent Ground-Truth Verification:[/bold green]")
    console.print(f"  Verified Status: {'[bold green]PASS[/bold green]' if packet.verification.is_verified else '[bold red]FAIL[/bold red]'}")
    console.print(f"  Confidence Score: {packet.verification.confidence_score * 100:.0f}%")
    console.print(f"  Evidence: {packet.verification.evidence}")
    
    # Query live ERP datastore
    invoice = default_erp.get_invoice("INV-X-2026-003")
    console.print("\n[bold cyan]ERP Database State Check:[/bold cyan]")
    console.print(f"  Invoice Number: [bold]{invoice.get('invoice_number')}[/bold]")
    console.print(f"  Vendor: [bold]{invoice.get('vendor_name')} ({invoice.get('vendor_id')})[/bold]")
    console.print(f"  Amount in Ledger: [bold]${invoice.get('amount', 0):,.2f}[/bold]")
    console.print(f"  Due Date in Ledger: [bold]{invoice.get('due_date')}[/bold]")
    console.print(f"  Status: [bold green]{invoice.get('status')}[/bold green]")
    
    console.print("\n[bold green]Summary Result:[/bold green]")
    console.print(packet.summary)

if __name__ == "__main__":
    run_invoice_demo()
