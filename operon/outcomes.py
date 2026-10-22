"""Ground user-facing failure explanations in the actions actually observed."""

import re
from pathlib import Path
from operon.memory.scratchpad import Scratchpad
from operon.state import TaskIssue


def value(record, key, default=None):
    return record.get(key, default) if isinstance(record, dict) else getattr(record, key, default)


def resource_name(task):
    text = task.casefold()
    if re.search(r"\b(quotation|quote)\b", text):
        return "quotation"
    if "invoice" in text:
        return "invoice"
    if "vendor" in text or "onboard" in text:
        return "vendor profile"
    if "blueprint" in text or "blue print" in text:
        return "blueprint"
    return "document"


def explain_failure(state, verification):
    """Do not turn an unattempted lookup or a tool error into a nonexistence claim."""
    memory = Scratchpad.from_dict(state.get("scratchpad", {}))
    task = state["task"]
    resource = resource_name(task)
    errors = [e for e in state.get("errors", []) if not value(e, "resolved", False)]
    error = errors[-1] if errors else None
    message = value(error, "message", "")
    error_type = value(error, "error_type", "")
    diagnostics = " ".join(verification.discrepancies if verification else [])

    def issue(code, title, text, next_step):
        return TaskIssue(code=code, title=title, message=text, next_step=next_step)

    if state.get("approval_rejected"):
        return issue("declined", "Stopped", "I stopped the task because you declined the pending action.",
                     "If you want to proceed later, review the action details and start the task again.")

    if memory.get_entity("search_no_results"):
        term = memory.get_entity("searched_term") or "the requested file"
        scope = "company documents, invoices, and vendor records" if memory.extracted_data.get("company_search") else "company files"
        return issue("resource_not_found", "Not found",
                     f"I couldn’t find a matching resource in the {scope} I searched for “{term}”. I can’t confirm whether it exists outside this workspace.",
                     "Check the customer, deal, or filename, or add the document to the workspace and send me its filename or path.")

    if error_type == "FileNotFoundError":
        step_id = value(error, "step_id")
        step = next((s for s in state.get("plan", []) if value(s, "step_id") == step_id), None)
        tool = value(step, "tool_name", "")
        args = value(step, "tool_args", {})
        if tool == "find_latest_signed_deal":
            customer = args.get("customer")
            subject = f" for {customer}" if customer else ""
            text = f"I couldn’t find a signed deal{subject} in the company deal records I checked, so I couldn’t retrieve its quotation."
            next_step = "Check the customer name or add the signed deal record and its linked quotation to the workspace, then try again."
        elif tool == "read_deal_quotation":
            deal = memory.extracted_data.get("deal_record", {})
            text = f"I found signed deal {deal.get('deal_id', args.get('deal_id', 'requested'))}, but its linked quotation {deal.get('quotation_id', '')} wasn’t found in the company quotation folder."
            next_step = "Add the linked quotation file or correct its filename in the deal record, then send “try again”."
        elif tool == "find_latest_invoice_file":
            company = args.get("company_name") or args.get("vendor_name") or args.get("company")
            subject = f" for {company}" if company else ""
            text = f"I couldn’t find a readable, dated source invoice{subject} in the invoice storage I checked."
            next_step = "Check the company name and source folder. Add a readable invoice with an issue date, amount, and due date, then ask me to try again."
        elif tool in ("search_files", "search_company_records"):
            text = "I couldn’t access the folder needed for this search, so I haven’t confirmed whether the document exists."
            next_step = "Check that the source folder exists and is readable, then send me the correct location."
        elif tool == "read_vendor_profile":
            company = args.get("company_name") or args.get("company") or "the requested vendor"
            text = f"I couldn’t find an onboarding profile for {company} in the available company files."
            next_step = "Check the vendor name or add its onboarding profile to the workspace, then try again."
        else:
            path = args.get("file_path") or args.get("path")
            name = Path(str(path)).name if path and "{{" not in str(path) else "the requested document"
            text = f"I couldn’t open {name} because it wasn’t found at the location checked."
            next_step = "Check the filename and location, or add the missing file to the workspace and send me its path."
        return issue("resource_not_found", "Source unavailable", text, next_step)

    if error_type == "AmbiguousResourceError":
        return issue("needs_clarification", "Which deal?", "More than one signed deal shares the latest signing date, so I couldn’t choose a quotation confidently.",
                     "Specify the customer to narrow the search, or correct the signing dates in the deal sources if they are inaccurate.")
    if error_type == "CompanySourceError":
        return issue("invalid_data", "Check company sources", "The deal or quotation source is unreadable, incomplete, or has conflicting details. I couldn’t verify the requested quotation.",
                     "Check the deal and quotation IDs, customer, signing date, amount, currency, and linked filename in the source records before retrying.")

    if not state.get("plan"):
        if error_type == "UnsupportedTask" and "bounded quotation workflow" in message:
            return issue("unsupported_task", "Quotation lookup only", "The quotation workflow can retrieve and verify the linked quotation for a customer’s latest signed deal. It can’t create, send, edit, or look up an arbitrary quotation ID.",
                         "Ask for the quotation from the latest signed deal, optionally naming a customer, or use company-record search to locate a specific ID.")
        if resource == "quotation" and re.search(r"\b(latest|signed|deal)\b", task, re.I):
            return issue("needs_clarification", "More information needed",
                         "I couldn’t retrieve that quotation. This run didn’t identify the latest signed deal or search its quotation files, so I can’t confirm whether the quotation exists.",
                         "Which customer or deal is this for? Share the quotation’s filename or location, or ask me to find the quotation file for a named customer.")
        if error_type == "ClarificationRequired":
            if resource == "invoice":
                detail = "I need a company name and a clear invoice request before I can proceed."
                next_step = "Which company is this for? For example: “Process the latest invoice from Company X and verify it.”"
            elif resource == "vendor profile":
                detail = "I need to know which vendor profile to use before I can register a vendor."
                next_step = "Send the vendor’s name and the location of its onboarding profile."
            else:
                detail = "I need a clearer task or source location before I can proceed."
                next_step = "Tell me which resource you mean and what you want me to do with it."
            return issue("needs_clarification", "More information needed", detail, next_step)
        return issue("unsupported_task", "Unavailable here",
                     "I can’t complete that request with the tools connected to this workspace. I haven’t confirmed whether the requested resource exists.",
                     "I can search local documents, process source invoices, or onboard vendors. Give me a task within those workflows and include the company or filename.")

    if "PreviewBlockedError" in message or error_type == "PreviewBlockedError":
        return issue("unsupported_task", "Unavailable in preview",
                     "This action isn’t supported by the isolated preview, so I stopped before performing it.",
                     "Use preview for company document and ERP workflows, or review the requested action before starting an actual run.")
    if "DuplicateInvoiceError" in message or "DuplicateVendorError" in message:
        return issue("conflict", "Record conflict",
                     "An existing ledger record has conflicting details. I stopped instead of replacing it.",
                     "Compare the source document with the existing record and resolve the conflicting fields before trying again.")
    if "InvalidAmountError" in message:
        return issue("invalid_data", "Check source amount", "The source amount is missing or invalid, so I couldn’t save the invoice.",
                     "Correct the source to include a positive amount, then ask me to process it again.")
    if "InvalidDateFormatError" in message:
        return issue("invalid_data", "Check source date", "The source due date isn’t a valid calendar date, so I couldn’t save the invoice.",
                     "Correct the source due date to YYYY-MM-DD, then ask me to process it again.")
    if "VendorNotFoundError" in message:
        return issue("resource_not_found", "Vendor not found", "I couldn’t match the source vendor to a registered vendor in the company ledger.",
                     "Check the vendor name or onboard the vendor from its source profile before processing this invoice.")
    if "MissingContextError" in message:
        return issue("needs_clarification", "Missing source details", "I couldn’t obtain all the source details needed for the next action.",
                     "Check that the document includes the required invoice or vendor fields, then send the corrected source location.")

    if error:
        tools = {
            "read_document": "read the document", "extract_invoice_data": "extract the invoice fields",
            "search_files": "search the company files", "write_file": "save the file",
            "erp_create_invoice": "save the invoice in the ledger", "erp_register_vendor": "register the vendor",
            "api_request": "complete the service request",
        }
        step = next((s for s in state.get("plan", []) if value(s, "step_id") == value(error, "step_id")), None)
        action = tools.get(value(step, "tool_name"), "complete the next action")
        return issue("tool_failed", "Could not complete", f"I couldn’t {action}. The task is unfinished.",
                     "Check the source or service is accessible, then try again. The activity details and evidence report contain the failed action.")

    if "source document changed" in diagnostics.casefold() or "no longer readable" in diagnostics.casefold():
        return issue("verification_failed", "Source changed", "I couldn’t confirm the outcome because a source document changed or became unreadable during the task.",
                     "Check the current source and any ledger changes before running the task again.")
    if "catalogue changed" in diagnostics.casefold() or "not the latest signed" in diagnostics.casefold():
        return issue("verification_failed", "Deal selection changed", "The deal sources changed during this task, so I couldn’t confirm which signed deal is latest.",
                     "Check the current deal sources, then ask me to try again so I can select and verify the latest signed deal from the current records.")
    if "mismatch" in diagnostics.casefold() or "differs from" in diagnostics.casefold():
        if resource == "quotation":
            return issue("verification_failed", "Quotation needs review", "The retrieved quotation doesn’t match its current source or signed deal, so I can’t mark this task complete.",
                         "Compare the quotation with the signed deal and correct the conflicting source details before retrying.")
        return issue("verification_failed", "Needs review", "The recorded result doesn’t match the source details, so I can’t mark this task complete.",
                     "Compare the source and ledger using the verification details. Correct the discrepancy before retrying.")
    if "search is incomplete" in diagnostics.casefold():
        return issue("verification_failed", "Search incomplete", "Some company files were unreadable or too large for the text search, so I couldn’t confirm a complete result.",
                     "Check the skipped files in the evidence report. Provide a readable text or JSON source, then try again.")
    return issue("verification_failed", "Could not verify", "I couldn’t verify that the requested outcome was achieved.",
                 "Review the task activity and verification details, check the source and any saved changes, then try again with a specific goal.")


def failure_message(state, issue, changed, mode):
    parts = [issue.message, issue.next_step]
    if mode == "preview":
        parts.append("This was a preview; the company ledger is unchanged.")
    elif changed:
        parts.append(f"{len(changed)} new ledger record(s) were created before the task stopped. Review them before retrying; they have not been rolled back.")
    else:
        read_only = {"search_files", "read_document", "find_latest_invoice_file", "extract_invoice_data",
                     "read_vendor_profile", "erp_lookup_vendor", "erp_get_invoice", "erp_list_invoices",
                     "erp_verify_invoice_status", "browser_get_dom", "find_latest_signed_deal",
                     "read_deal_quotation", "search_company_records"}
        actions = state.get("action_history", [])
        if all(value(a, "tool_name") in read_only for a in actions):
            parts.append("No changes were made.")
        else:
            parts.append("Check the activity and ledger before retrying; earlier actions may have taken effect.")
    return "\n\n".join(parts)
