"""Conversational entry point for goals and questions about recorded outcomes."""

import re
from operon.validation import parse_amount


def _invoice_from_packet(packet):
    for action in reversed(packet.get("action_log", [])):
        record = action.get("observation")
        if isinstance(record, dict) and record.get("invoice_number") and record.get("amount") is not None:
            return record
        if isinstance(record, dict) and isinstance(record.get("invoice_record"), dict):
            return record["invoice_record"]
    return next((r for r in packet.get("created_records", []) if "invoice_number" in r), None)


def _quotation_from_packet(packet):
    for action in reversed(packet.get("action_log", [])):
        observation = action.get("observation")
        if isinstance(observation, dict) and observation.get("quotation_record"):
            return observation["quotation_record"], observation.get("deal_record", {})
    return None, None


def chat_reply(message, previous=None):
    """Return a grounded reply, a preview execution request, or a new goal.

    A reply never invokes tools. Work and approval decisions are performed by the
    existing run manager after this routing decision.
    """
    clean = re.sub(r"[^\w\s]", "", message.casefold()).strip()
    if previous and previous.get("status") == "waiting_approval":
        if clean in {"yes", "approve", "approved", "yes approve", "go ahead", "proceed"}:
            return {"kind": "decision", "approved": True}
        if clean in {"no", "reject", "decline", "cancel", "stop", "no thanks"}:
            return {"kind": "decision", "approved": False}
        return {"kind": "reply", "reply": "I’m ready to continue, but I need your decision on the action shown below. Say ‘approve’ to continue or ‘decline’ to stop."}

    if clean in {"hi", "hello", "hey", "hi operon", "hello operon", "good morning", "good evening"}:
        return {"kind": "reply", "reply": "Hi! What can I help you get done? I can work with company files, invoices, quotations, and vendor records, then check the result for you."}
    if clean in {"thanks", "thank you", "thanks operon", "thank you operon"}:
        return {"kind": "reply", "reply": "Anytime. What should we tackle next?"}
    if clean in {"yes", "no", "ok", "okay"}:
        return {"kind": "reply", "reply": "Sure—what would you like me to handle next? You can also ask me about the last result."}
    if clean in {"help", "what can you do", "how can you help", "can you help me", "who are you", "how are you"}:
        return {"kind": "reply", "reply": "I can help with work in this company sandbox: finding documents, processing invoices, onboarding vendors, retrieving a signed deal’s quotation, and searching company records. You can preview a task first, and I’ll show you the sources and checks behind the result."}

    if clean in {"try again", "retry", "retry it", "try that again"}:
        if previous and previous.get("status") in {"failed", "partially_completed", "interrupted"}:
            return {"kind": "task", "task": previous["task"], "mode": previous.get("mode", "execute")}
        return {"kind": "reply", "reply": "I don’t have a failed task to retry in this conversation yet. Tell me what you’d like me to try."}

    if clean in {"why", "why not", "what went wrong", "what should i do now", "what next", "what do you need", "what do you need from me", "how can i fix it"}:
        packet = (previous or {}).get("packet") or {}
        if packet.get("issue"):
            return {"kind": "reply", "reply": packet["agent_message"]}
        return {"kind": "reply", "reply": "Tell me what you’d like done, or ask me about an amount, source document, or check from the last result."}

    if clean in {"run it", "do it", "go ahead", "execute it", "register it", "enter it", "commit the preview"}:
        packet = (previous or {}).get("packet") or {}
        if previous and previous.get("mode") == "preview" and (packet.get("verification") or {}).get("is_verified"):
            return {"kind": "task", "task": previous["task"], "mode": "execute"}
        return {"kind": "reply", "reply": "Tell me the task you want me to run, or finish a verified preview first. That keeps the action you’re authorizing clear."}

    question = re.match(r"^(what|whats|which|when|how|why|show me|tell me|is it|did it)\b", clean)
    field_question = question and re.search(r"\b(amount|much|total|balance|due|deadline|date|vendor|source|document|evidence|status|happen|failed|fail|wrong|verify|verified|checks|did you do|deal|customer|valid|signed)\b", clean)
    new_goal = re.search(r"\b(latest|register|onboard|enter|process|create|find|search|new)\b", clean)
    if field_question and not new_goal:
        packet = (previous or {}).get("packet")
        if not packet:
            return {"kind": "reply", "reply": "I don’t have a finished result in this conversation yet. Give me a task first, and I’ll explain what I find after I’ve checked it."}
        verified = bool((packet.get("verification") or {}).get("is_verified"))
        caveat = "" if verified else " This run did not pass verification; these are the recorded values, not a confirmed outcome."
        invoice = _invoice_from_packet(packet)
        quote, deal = _quotation_from_packet(packet)
        prefix = "In the preview, the " if (previous or {}).get("mode") == "preview" else "The "
        if re.search(r"\b(verify|verified|checks)\b", clean):
            checks = (packet.get("verification") or {}).get("checks_performed", [])
            return {"kind": "reply", "reply": ("I checked: " + "; ".join(checks) + "." if checks else "This report has no independent verification checks.") + caveat}
        if re.search(r"\b(amount|much|total|balance)\b", clean) and invoice:
            try:
                amount = parse_amount(invoice.get("amount"))
            except ValueError:
                return {"kind": "reply", "reply": "This report does not contain a valid recorded amount." + caveat}
            return {"kind": "reply", "reply": prefix + f"recorded amount for {invoice['invoice_number']} is USD {amount:,.2f}." + caveat}
        if re.search(r"\b(due|deadline|date)\b", clean) and invoice and invoice.get("due_date"):
            return {"kind": "reply", "reply": prefix + f"due date recorded for {invoice['invoice_number']} is {invoice['due_date']}." + caveat}
        if "vendor" in clean and invoice and invoice.get("vendor_id"):
            return {"kind": "reply", "reply": prefix + f"invoice is recorded under {invoice.get('vendor_name') or invoice['vendor_id']} ({invoice['vendor_id']})." + caveat}
        if quote and re.search(r"\b(amount|much|total|balance)\b", clean):
            return {"kind": "reply", "reply": f"Quotation {quote['quotation_id']} records {quote['currency']} {parse_amount(quote['amount']):,.2f} for {quote['customer']}." + caveat}
        if quote and re.search(r"\b(valid|deadline|date)\b", clean) and "signed" not in clean:
            return {"kind": "reply", "reply": f"Quotation {quote['quotation_id']} lists a validity deadline of {quote['valid_until']}." + caveat}
        if deal and re.search(r"\b(deal|customer|signed)\b", clean):
            return {"kind": "reply", "reply": f"The selected deal is {deal['deal_id']} for {deal['customer']}, signed on {deal['signed_at']}." + caveat}
        if re.search(r"\b(source|document|evidence)\b", clean):
            files = [str(d['file_path']).replace('\\', '/').rsplit('/', 1)[-1] for d in packet.get("source_documents", [])]
            reply = "I used " + ", ".join(files) + ". The evidence download includes the source hashes, action log, and verification checks." if files else "This report has no captured source documents. You can inspect the action log in the evidence download."
            return {"kind": "reply", "reply": reply + caveat}
        return {"kind": "reply", "reply": packet.get("agent_message") or packet.get("summary") or "That detail was not captured in this task’s report." + caveat}
    return {"kind": "task", "task": message}
