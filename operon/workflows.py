"""Small, data-driven offline workflows for the supplied company environment."""

import json
import re
from operon.config import settings
from operon.environment.context import get_erp

SUPPORTED_TOOLS = {
    "find_latest_invoice_file", "read_document", "search_files", "extract_invoice_data",
    "read_vendor_profile", "write_file",
    "erp_lookup_vendor", "erp_create_invoice", "erp_get_invoice",
    "erp_list_invoices", "erp_register_vendor", "erp_verify_invoice_status", "erp_delete_record",
    "browser_navigate", "browser_fill_form", "browser_get_dom",
    "api_request",
    "find_latest_signed_deal", "read_deal_quotation", "search_company_records",
}


def step(number, description, tool, args):
    return {"step_id": number, "description": description, "tool_name": tool,
            "tool_args": args, "expected_outcome": description}


def offline_plan(task):
    lowered = task.casefold()
    if any(phrase in lowered for phrase in ("company records", "workspace records", "across the workspace", "everything related to")):
        match = re.search(r"(?:\bfor\b|\babout\b|related to)\s+(.+?)[.!?]*$", task, re.I)
        if not match:
            return {"steps": [], "error": "Specify a company, record ID, or keyword to search across company records."}
        return {"steps": [step(1, "Search company sources and ledger records", "search_company_records", {"query": match.group(1).strip(' \"“”')})]}
    if re.search(r"\b(quotation|quote)\b", lowered):
        if re.search(r"\b(create|draft|send|email|delete|update|edit)\b", lowered) or re.search(r"\b(?:QT|DEAL)-[A-Za-z0-9-]+", task, re.I):
            return {"steps": [], "error_type": "UnsupportedTask", "error": "The bounded quotation workflow retrieves the linked quotation for the latest signed deal, optionally by customer."}
        customer = ""
        aliases = [(len(alias), vendor["name"]) for vendor in get_erp().vendors.values()
                   for alias in [vendor["name"], *vendor.get("alias", [])]
                   if re.search(r"\b" + re.escape(alias.casefold()) + r"\b", lowered)]
        if aliases:
            customer = max(aliases)[1]
        else:
            for match in re.finditer(r"\b(?:for|from|with|customer|by)\s+", task, re.I):
                candidate = re.split(r"[,.;!?]|\band\b|\bthen\b", task[match.end():], maxsplit=1, flags=re.I)[0].strip()
                if candidate and not re.match(r"(?:the\s+)?(?:latest|last|most recent|signed|deal)\b", candidate, re.I):
                    customer = candidate
                    break
        return {"steps": [
            step(1, "Find the latest signed deal from source records", "find_latest_signed_deal", {"customer": customer}),
            step(2, "Read and check the quotation linked to that deal", "read_deal_quotation", {"deal_id": "{{deal_id}}"}),
        ]}
    if "invoice" in lowered:
        matches = []
        for vendor in get_erp().vendors.values():
            for alias in [vendor["name"], *vendor.get("alias", [])]:
                if re.search(r"\b" + re.escape(alias.casefold()) + r"\b", lowered):
                    matches.append((len(alias), vendor["name"]))
        if not matches:
            return {"steps": [], "error": "Specify a known company for invoice processing: Company X, Acme, Globex, Balaji, or OmniCorp."}
        company = max(matches)[1]
        if "latest" not in lowered and "recent" not in lowered:
            return {"steps": [], "error": "Offline invoice processing supports the latest source invoice. Ask to process the latest invoice for a company."}
        return {"steps": [
            step(1, f"Find the latest source invoice for {company}", "find_latest_invoice_file", {"company_name": company}),
            step(2, "Resolve the registered vendor", "erp_lookup_vendor", {"query": "{{vendor_name}}"}),
            step(3, "Register the source invoice in the ledger", "erp_create_invoice", {
                "invoice_number": "{{invoice_number}}", "vendor_id": "{{vendor_id}}",
                "amount": "{{amount}}", "due_date": "{{due_date}}"}),
            step(4, "Check the stored amount and due date", "erp_verify_invoice_status", {
                "invoice_number": "{{invoice_number}}", "expected_amount": "{{amount}}", "expected_due_date": "{{due_date}}"}),
        ]}
    if any(word in lowered for word in ("vendor", "onboard", "register")):
        for path in sorted((settings.sample_data_dir / "vendors").glob("*.json")):
            profile = json.loads(path.read_text(encoding="utf-8"))
            name = profile.get("company_name") or profile.get("name", "")
            if name and re.search(r"\b" + re.escape(name.split()[0].casefold()) + r"\b", lowered):
                return {"steps": [
                    step(1, f"Read the onboarding profile for {name}", "read_vendor_profile", {"company_name": name}),
                    step(2, "Register the verified vendor details", "erp_register_vendor", {
                        "name": "{{vendor_name}}", "tax_id": "{{tax_id}}",
                        "payment_terms": "{{payment_terms}}", "contact_email": "{{contact_email}}"}),
                ]}
        return {"steps": [], "error": "Specify a vendor with a local onboarding profile: Apex, Quantum, Horizon, Cyberdyne, or Balaji."}
    if any(word in lowered for word in ("blueprint", "document", "spec", "drawing", "file", "search", "find", "read")):
        stop_words = {"the", "of", "find", "a", "an", "and", "in", "to", "for", "please", "me", "show", "get", "read", "look", "up"}
        words = [w for w in re.findall(r"[a-z0-9]+", lowered) if w not in stop_words]
        term = words[0] if words else "balaji"
        return {"steps": [
            step(1, f"Search storage for '{term}' files and documents", "search_files", {"pattern": f"*{term}*"}),
            step(2, f"Read the discovered document content", "read_document", {"file_path": "{{file_path}}"}),
        ]}
    return {"steps": [], "error_type": "UnsupportedTask", "error": "This action cannot be completed with the available tools in the supplied sandbox."}
