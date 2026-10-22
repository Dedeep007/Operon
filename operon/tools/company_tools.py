"""Read-only company discovery and source-linked deal/quotation tools."""

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from operon.config import settings
from operon.environment.context import get_erp
from operon.tools.registry import registry
from operon.validation import parse_amount


class AmbiguousResourceError(ValueError):
    pass


class CompanySourceError(ValueError):
    pass


def source_document(path):
    return {"file_path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def customer_matches(query, name):
    tokens = re.findall(r"[a-z0-9]+", query.casefold())
    words = re.findall(r"[a-z0-9]+", name.casefold())
    return all(t in words for t in tokens)


def load_deals():
    directory = settings.sample_data_dir / "deals"
    if not directory.is_dir():
        raise FileNotFoundError("The company deal folder is unavailable.")
    records = []
    seen = set()
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not all(data.get(k) for k in ("deal_id", "customer", "status", "quotation_id", "quotation_file")):
                raise ValueError("Missing deal fields")
            if data["deal_id"] in seen:
                raise ValueError("Duplicate deal ID")
            seen.add(data["deal_id"])
            if data["status"] not in {"signed", "draft", "cancelled"}:
                raise ValueError("Unknown deal status")
            if data["status"] == "signed":
                if date.fromisoformat(data["signed_at"]).isoformat() != data["signed_at"]:
                    raise ValueError("Signing date must use YYYY-MM-DD")
            parse_amount(data["amount"])
            if not re.fullmatch(r"[A-Z]{3}", data["currency"]):
                raise ValueError("Invalid currency")
            records.append({"record": data, **source_document(path)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CompanySourceError(f"The deal source '{path.name}' is unreadable or invalid; latest-deal selection cannot be confirmed.") from exc
    return records


@registry.register(name="find_latest_signed_deal", description="Find the latest signed deal by its actual signed_at date in local company JSON sources. Optional customer filter. Excludes drafts/cancelled deals and returns a source selection manifest; equal dates require clarification.")
def find_latest_signed_deal(customer: str = ""):
    customer = str(customer or "").strip()
    catalogue = load_deals()
    eligible = [d for d in catalogue if d["record"]["status"] == "signed"
                and (not customer.strip() or customer_matches(customer.strip(), d["record"]["customer"]))]
    if not eligible:
        raise FileNotFoundError(f"No signed deal found for '{customer or 'any customer'}' in the company deal sources.")
    eligible.sort(key=lambda d: d["record"]["signed_at"], reverse=True)
    if len(eligible) > 1 and eligible[0]["record"]["signed_at"] == eligible[1]["record"]["signed_at"]:
        raise AmbiguousResourceError("Multiple signed deals share the latest date. Specify a customer to disambiguate.")
    chosen = eligible[0]
    return {"deal_record": chosen["record"], "file_path": chosen["file_path"], "sha256": chosen["sha256"],
            "selection_manifest": [{"file_path": d["file_path"], "sha256": d["sha256"]} for d in catalogue],
            "customer_query": customer.strip(), "eligible_count": len(eligible)}


@registry.register(name="read_deal_quotation", description="Read the quotation linked to an existing signed deal_id from company sources. Checks the linked path stays in the quotations folder and the quotation ID, customer, amount, currency, and deal reference match. Never substitutes another quotation when the link is missing.")
def read_deal_quotation(deal_id: str):
    deal = next((d for d in load_deals() if d["record"]["deal_id"] == deal_id), None)
    if not deal:
        raise FileNotFoundError(f"Deal '{deal_id}' was not found in company sources.")
    record = deal["record"]
    if record["status"] != "signed":
        raise CompanySourceError("The selected deal is not signed.")
    root = (settings.sample_data_dir / "quotations").resolve()
    path = (root / record["quotation_file"]).resolve()
    if not path.is_relative_to(root) or path.suffix.casefold() != ".json":
        raise CompanySourceError("The linked quotation must be a JSON source inside the company quotations folder.")
    if not path.is_file():
        raise FileNotFoundError(f"The linked quotation '{record['quotation_id']}' for deal '{deal_id}' is missing from company storage.")
    try:
        quote = json.loads(path.read_text(encoding="utf-8"))
        for key in ("quotation_id", "deal_id", "customer", "currency"):
            if quote[key] != record[key]:
                raise ValueError(f"Mismatched {key}")
        if parse_amount(quote["amount"]) != parse_amount(record["amount"]):
            raise ValueError("Mismatched amount")
        date.fromisoformat(quote["valid_until"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CompanySourceError("The linked quotation is unreadable or its details do not match the signed deal.") from exc
    document = source_document(path)
    return {"quotation_record": quote, "deal_record": record, **document,
            "source_documents": [{"file_path": deal["file_path"], "sha256": deal["sha256"]}, document]}


@registry.register(name="search_company_records", description="Read-only search across local company document contents, ledger invoices, and vendor records. query is required. Returns typed matches, excerpts, record snapshots and source hashes, plus skipped-file warnings. limit is 1 to 50.")
def search_company_records(query: str, limit: int = 12):
    tokens = re.findall(r"[a-z0-9]+", query.casefold())
    if not tokens:
        raise ValueError("A company name, record ID, or document keyword is required.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("Search limit must be between 1 and 50.")

    def matches(text):
        return all(t in text.casefold() for t in tokens)

    results, skipped = [], []
    root = settings.sample_data_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError("Company source storage is unavailable.")
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in {".txt", ".json", ".md", ".csv"}:
            continue
        if not path.resolve().is_relative_to(root):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                skipped.append(path.name)
                continue
            content = path.read_text(encoding="utf-8")
            if matches(path.name + " " + content):
                position = content.casefold().find(tokens[0])
                start = max(0, position - 40)
                results.append({"kind": "document", "label": path.name, "reference": str(path.resolve()),
                                "excerpt": content[start:start + 240], **source_document(path)})
        except (OSError, UnicodeError):
            skipped.append(path.name)
    snapshot = get_erp().get_state_snapshot()
    for kind, key, id_field, label_field in (("invoice", "invoices", "invoice_number", "invoice_number"),
                                             ("vendor", "vendors", "vendor_id", "name")):
        for record in snapshot[key].values():
            if matches(json.dumps(record, ensure_ascii=False)):
                results.append({"kind": kind, "label": record[label_field], "reference": record[id_field], "record": record})
    return {"query": query, "matches": results[:limit], "total_matches": len(results),
            "truncated": len(results) > limit, "skipped_files": skipped,
            "searched": ["company document contents", "ledger invoices", "vendor directory"]}
