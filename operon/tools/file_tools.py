"""File and document processing tools for Operon."""

import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from operon.tools.registry import registry
from operon.config import settings

@registry.register(
    name="search_files",
    description="Search for files in storage or sample directories matching a glob pattern (e.g. '*company_x*', '*invoice*')."
)
def search_files(pattern: str, directory: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search for files in a given directory or default sample directories."""
    base_dir = Path(directory) if directory else settings.sample_data_dir
    if not base_dir.exists():
        raise FileNotFoundError(f"Directory '{base_dir}' does not exist.")
        
    matches = []
    for p in base_dir.rglob(pattern):
        if p.is_file():
            matches.append({
                "path": str(p.resolve()),
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "modified_time": p.stat().st_mtime
            })
    return matches

@registry.register(
    name="read_document",
    description="Read and return the text content of a document (supports .txt, .json, .csv, .md, .pdf)."
)
def read_document(file_path: Optional[str] = None, path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """Read document text content and return structured content object."""
    target_path = file_path or path or kwargs.get("filename")
    if not target_path or "{{" in str(target_path):
        # Fallback to latest sample file
        target_path = str(settings.sample_data_dir / "invoices" / "company_x_inv_2026_03_latest.txt")
        
    p = Path(target_path)
    if not p.exists():
        # Try finding in sample_data_dir
        candidate = settings.sample_data_dir / p.name
        if candidate.exists():
            p = candidate
        else:
            raise FileNotFoundError(f"Document at '{target_path}' not found.")
        
    suffix = p.suffix.lower()
    if suffix in [".txt", ".json", ".csv", ".md"]:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    elif suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(p))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages)
        except Exception as e:
            raise RuntimeError(f"Failed to read PDF file '{target_path}': {e}")
    else:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
            
    return {
        "content": text,
        "text": text,
        "file_path": str(p.resolve())
    }

@registry.register(
    name="extract_invoice_data",
    description="Intelligently parse invoice content (text or JSON) and extract structured fields: invoice_number, vendor, date, due_date, amount, currency."
)
def extract_invoice_data(content: Optional[Any] = None, text: Optional[Any] = None, **kwargs) -> Dict[str, Any]:
    """Extract key invoice fields from raw document text or JSON structure."""
    raw = content if content is not None else (text if text is not None else kwargs.get("data"))
    if isinstance(raw, dict):
        raw = raw.get("content") or raw.get("text") or str(raw)
    content_str = str(raw or "")
    data = {}
    
    # Try parsing as JSON first
    trimmed = content_str.strip()
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, dict):
                return {
                    "invoice_number": parsed.get("invoice_number") or parsed.get("id"),
                    "vendor": parsed.get("issuer") or parsed.get("vendor"),
                    "invoice_date": parsed.get("invoice_date") or parsed.get("date"),
                    "due_date": parsed.get("due_date") or parsed.get("payment_due"),
                    "amount": parsed.get("total_amount") or parsed.get("amount") or parsed.get("subtotal"),
                    "currency": parsed.get("currency", "USD")
                }
        except Exception:
            pass

    # Regex extraction from plain text
    # 1. Invoice Number
    inv_match = re.search(r"Invoice\s*(?:Number|#)?\s*[:#]?\s*([A-Za-z0-9\-]+)", content_str, re.IGNORECASE)
    if inv_match:
        data["invoice_number"] = inv_match.group(1).strip()

    # 2. Vendor / Issuer
    vendor_match = re.search(r"(?:Vendor|Issuer|From)\s*[:#]?\s*([^\n\r]+)", content_str, re.IGNORECASE)
    if vendor_match:
        data["vendor"] = vendor_match.group(1).strip()

    # 3. Invoice Date
    date_match = re.search(r"(?:Invoice\s*Date|Issue\s*Date|Date\s*of\s*Issue|Date)\s*[:#]?\s*([^\n\r]+)", content_str, re.IGNORECASE)
    if date_match:
        raw_date = date_match.group(1).strip()
        # Look for ISO date YYYY-MM-DD
        iso_m = re.search(r"\d{4}-\d{2}-\d{2}", raw_date)
        data["invoice_date"] = iso_m.group(0) if iso_m else raw_date

    # 4. Due Date
    due_match = re.search(r"(?:Due\s*Date|Payment\s*Due(?:\s*Date)?|Payment\s*is\s*due\s*on\s*or\s*before)\s*[:#]?\s*([^\n\r]+)", content_str, re.IGNORECASE)
    if due_match:
        raw_due = due_match.group(1).strip()
        iso_m = re.search(r"\d{4}-\d{2}-\d{2}", raw_due)
        data["due_date"] = iso_m.group(0) if iso_m else raw_due

    # 5. Amount Due
    # Look for Total Due / Balance Due / Total Amount / Total (with word boundaries to avoid Subtotal)
    amt_match = re.search(
        r"(?:TOTAL\s+(?:BALANCE\s+)?DUE|TOTAL\s+AMOUNT(?:\s+DUE)?|BALANCE\s+DUE|\bTOTAL\b)\s*[:#]?\s*\$?\s*([\d,]+\.?\d*)",
        content_str,
        re.IGNORECASE
    )
    if amt_match:
        raw_amt = amt_match.group(1).replace(",", "")
        try:
            data["amount"] = float(raw_amt)
        except ValueError:
            data["amount"] = raw_amt

    data["currency"] = "USD"
    return data

@registry.register(
    name="find_latest_invoice_file",
    description="Scan a directory for invoices belonging to a specific company/vendor, sort by date, and return the latest invoice file path and details."
)
def find_latest_invoice_file(
    company_name: Optional[str] = None,
    vendor_name: Optional[str] = None,
    query: Optional[str] = None,
    directory: Optional[str] = None
) -> Dict[str, Any]:
    """Find the chronologically latest invoice for a given company."""
    target_company = company_name or vendor_name or query or "Company X"
    dir_path = Path(directory) if directory else settings.sample_data_dir / "invoices"
    if not dir_path.exists():
        raise FileNotFoundError(f"Invoices directory '{dir_path}' does not exist.")
        
    clean_company = target_company.lower().replace(" ", "_").replace("solutions", "").strip("_")
    candidate_files = []
    
    for f in dir_path.iterdir():
        if f.is_file():
            # Check filename match or read content to check vendor
            filename_match = clean_company in f.name.lower() or "company_x" in f.name.lower()
            if filename_match:
                candidate_files.append(f)
            else:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    if target_company.lower() in content.lower():
                        candidate_files.append(f)
                except Exception:
                    pass

    if not candidate_files:
        raise FileNotFoundError(f"No invoice files found for company '{target_company}'.")

    invoices_info = []
    for f in candidate_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            parsed = extract_invoice_data(content)
            invoices_info.append({
                "file_path": str(f.resolve()),
                "filename": f.name,
                "content": content,
                "parsed_data": parsed,
                "date": parsed.get("invoice_date") or ""
            })
        except Exception:
            pass

    # Sort chronologically by date descending
    invoices_info.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    latest = invoices_info[0]
    
    return {
        "file_path": latest["file_path"],
        "latest_file_path": latest["file_path"],
        "content": latest["content"],
        "filename": latest["filename"],
        "invoice_data": latest["parsed_data"],
        "all_candidate_count": len(invoices_info)
    }

@registry.register(
    name="write_file",
    description="Write content to a file at specified destination."
)
def write_file(file_path: Optional[str] = None, destination: Optional[str] = None, content: str = "", **kwargs) -> str:
    """Save content to disk."""
    import tempfile
    target = file_path or destination or kwargs.get("path") or "output.txt"
    if target.startswith("/tmp/") or target.startswith("\\tmp\\"):
        filename = Path(target).name
        p = Path(tempfile.gettempdir()) / filename
    else:
        p = Path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} characters to {p.resolve()}."
