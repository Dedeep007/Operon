"""Demo: Autonomous Vendor Onboarding (Generalization Capability).

Task:
"Read the vendor profile for Apex Technologies from file, and register them
into our internal ERP accounting system."
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from operon.agent import OperonAgent
from operon.environment.erp_system import default_erp
from rich.console import Console
from rich.panel import Panel

console = Console()

def run_vendor_demo():
    console.print(Panel(
        "[bold cyan]TASK:[/bold cyan] Read the vendor profile for Apex Technologies from file, and register them into our internal ERP system.",
        title="[bold green]Operon Generalization Demo: Vendor Onboarding[/bold green]",
        border_style="magenta"
    ))
    
    agent = OperonAgent()
    packet = agent.run("Read the vendor profile for Apex Technologies from file, and register them into our internal ERP system.")
    
    console.print(f"\n[bold]Execution Status:[/bold] [bold green]{packet.status.upper()}[/bold green]")
    console.print(f"[bold]Total Actions Taken:[/bold] {packet.total_actions_taken}")
    console.print(f"[bold]Duration:[/bold] {packet.execution_time_seconds}s")
    
    # Check ERP vendor registration
    vendor = default_erp.find_vendor("Apex Technologies")
    if vendor:
        console.print("\n[bold green]Vendor Successfully Registered in ERP Ledger:[/bold green]")
        console.print(f"  Vendor ID: [bold]{vendor.get('vendor_id')}[/bold]")
        console.print(f"  Company Name: [bold]{vendor.get('name')}[/bold]")
        console.print(f"  Tax ID: [bold]{vendor.get('tax_id')}[/bold]")
        console.print(f"  Payment Terms: [bold]{vendor.get('payment_terms')}[/bold]")
        console.print(f"  Contact Email: [bold]{vendor.get('contact_email')}[/bold]")
    else:
        console.print("[bold red]Vendor not found in ERP.[/bold red]")

if __name__ == "__main__":
    run_vendor_demo()
