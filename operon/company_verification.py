"""Independent source/ledger checks for company discovery workflows."""

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from operon.config import settings
from operon.environment.context import get_erp
from operon.validation import parse_amount


def verify_deal_quotation(memory):
    checks = ["Re-read deal catalogue and verify latest signed date", "Verify quotation belongs to the selected signed deal"]
    discrepancies, evidence = [], []
    deal = memory.extracted_data.get("deal_record")
    quote = memory.extracted_data.get("quotation_record")
    manifest = memory.extracted_data.get("deal_selection_manifest")
    if not deal or not quote or manifest is None:
        return checks, ["A signed-deal selection and linked quotation were not both captured."], evidence
    try:
        files = sorted((settings.sample_data_dir / "deals").glob("*.json"))
        current_manifest = [{"file_path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
        if current_manifest != manifest:
            discrepancies.append("The deal catalogue changed after selection; latest-deal selection must be repeated.")
        query = memory.extracted_data.get("deal_customer_query", "")
        tokens = re.findall(r"[a-z0-9]+", query.casefold())
        candidates = []
        for path in files:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["status"] != "signed":
                continue
            signed = date.fromisoformat(record["signed_at"])
            customer_words = re.findall(r"[a-z0-9]+", record["customer"].casefold())
            if all(t in customer_words for t in tokens):
                candidates.append((signed, record))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates or candidates[0][1] != deal:
            discrepancies.append("The selected deal is not the latest signed source deal for the requested customer scope.")
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            discrepancies.append("The latest signed deal is ambiguous; multiple deals share its signing date.")
        root = (settings.sample_data_dir / "quotations").resolve()
        path = (root / deal["quotation_file"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Quotation outside company source folder")
        actual_quote = json.loads(path.read_text(encoding="utf-8"))
        if quote != actual_quote:
            discrepancies.append("The captured quotation differs from its source document.")
        for key in ("quotation_id", "deal_id", "customer", "currency"):
            checks.append(f"Verify quotation {key.replace('_', ' ')} against signed deal")
            if actual_quote[key] != deal[key]:
                discrepancies.append(f"Quotation {key} does not match the selected signed deal.")
        checks.append("Verify quotation amount against signed deal")
        if parse_amount(actual_quote["amount"]) != parse_amount(deal["amount"]):
            discrepancies.append("Quotation amount does not match the selected signed deal.")
        date.fromisoformat(actual_quote["valid_until"])
        if not discrepancies:
            evidence.append(f"Latest signed deal: {deal['deal_id']} ({deal['signed_at']}) for {deal['customer']}")
            evidence.append(f"Linked quotation: {quote['quotation_id']} | {quote['currency']} {parse_amount(quote['amount']):,.2f} | source and deal fields match")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        discrepancies.append(f"Deal/quotation sources could not be independently checked: {type(exc).__name__}.")
    return checks, discrepancies, evidence


def verify_company_search(memory):
    checks = ["Verify company search scope and captured matches"]
    discrepancies, evidence = [], []
    search = memory.extracted_data.get("company_search")
    if not search:
        return checks, ["No company search result was captured."], evidence
    if search.get("skipped_files"):
        discrepancies.append("Some company files could not be searched; the search is incomplete.")
    snapshot = get_erp().get_state_snapshot()
    tokens = re.findall(r"[a-z0-9]+", search["query"].casefold())
    for match in search["matches"]:
        if match["kind"] == "document":
            try:
                path = Path(match["file_path"])
                content = path.name + " " + path.read_text(encoding="utf-8")
                if not all(t in content.casefold() for t in tokens):
                    discrepancies.append("A captured document no longer matches the search query.")
            except (OSError, UnicodeError):
                discrepancies.append("A matched document is no longer readable.")
        else:
            key = "invoices" if match["kind"] == "invoice" else "vendors"
            if snapshot[key].get(match["reference"]) != match["record"]:
                discrepancies.append("A matched ledger record changed after the search.")
    if search["matches"] and not discrepancies:
        evidence.append(f"Found {search['total_matches']} matches for '{search['query']}' across company documents, ledger invoices, and vendor records; {len(search['matches'])} captured for review")
    return checks, discrepancies, evidence
