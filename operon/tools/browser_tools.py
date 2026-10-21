"""Simulated web browser tools for interacting with web portals and intranet applications."""

from typing import Dict, Any, Optional
from operon.tools.registry import registry

# In-memory browser state for simulated intranet navigation
_browser_sessions: Dict[str, Dict[str, Any]] = {
    "https://portal.internal/invoices/new": {
        "title": "Internal Accounting Portal - Enter Invoice",
        "inputs": ["vendor_name", "invoice_num", "amount", "due_date"],
        "status": "ready"
    },
    "https://portal.internal/vendors/onboard": {
        "title": "Vendor Onboarding Portal",
        "inputs": ["company_name", "tax_id", "email"],
        "status": "ready"
    }
}

@registry.register(
    name="browser_navigate",
    description="Navigate to an internal or external web page URL."
)
def browser_navigate(url: str) -> Dict[str, Any]:
    """Visit a web page and return the page title and status."""
    clean_url = url.strip()
    session = _browser_sessions.get(clean_url, {
        "title": f"Page at {clean_url}",
        "inputs": [],
        "status": "loaded"
    })
    return {
        "url": clean_url,
        "title": session["title"],
        "status": 200,
        "message": f"Successfully loaded {clean_url}"
    }

@registry.register(
    name="browser_fill_form",
    description="Fill and submit an HTML form on the current web page."
)
def browser_fill_form(url: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate form submission on internal web portal."""
    clean_url = url.strip()
    return {
        "url": clean_url,
        "submitted_data": form_data,
        "success": True,
        "response_message": "Form submitted successfully. Record queued for processing."
    }

@registry.register(
    name="browser_get_dom",
    description="Inspect the DOM or text content of the currently loaded page."
)
def browser_get_dom(url: str) -> str:
    """Retrieve rendered DOM structure of a page."""
    clean_url = url.strip()
    session = _browser_sessions.get(clean_url, {
        "title": f"Page at {clean_url}",
        "inputs": []
    })
    return f"<html><head><title>{session['title']}</title></head><body><h1>{session['title']}</h1><div>Inputs: {session['inputs']}</div></body></html>"
