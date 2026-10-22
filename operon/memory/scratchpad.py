"""Context Working Memory and Scratchpad for Operon.

Maintains discovered entities, cross-step state, extracted parameters,
and allows dynamic reference interpolation between execution steps.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import re
from pydantic import BaseModel, Field
from operon.safety.data_policy import classify_resource

class Scratchpad(BaseModel):
    """Working memory tracking information discovered during agent execution."""
    entities: Dict[str, Any] = Field(default_factory=dict, description="Named entities e.g. vendor_id, invoice_number")
    extracted_data: Dict[str, Any] = Field(default_factory=dict, description="Raw extracted structures")
    files_found: List[str] = Field(default_factory=list, description="Discovered file paths")
    step_results: Dict[int, Any] = Field(default_factory=dict, description="Results indexed by step_id")
    notes: List[str] = Field(default_factory=list, description="Reasoning notes accumulated during task")
    source_documents: List[Dict[str, Any]] = Field(default_factory=list)

    def record_entity(self, key: str, value: Any):
        """Store an entity in working memory."""
        self.entities[key] = value

    def add_note(self, note: str):
        """Append a unique observation note to working memory."""
        if note and note not in self.notes:
            self.notes.append(note)

    def get_entity(self, key: str, default: Any = None) -> Any:
        """Retrieve an entity from working memory."""
        return self.entities.get(key, default)

    def add_source_document(self, document: Dict[str, Any]):
        """Capture a source hash together with its policy classification."""
        if not document.get("file_path") or not document.get("sha256"):
            return
        captured = dict(document)
        try:
            classification = classify_resource(captured["file_path"])
            captured.update({
                "data_classification": classification.data_classification,
                "data_categories": classification.data_categories,
                "policy_id": classification.policy_id,
            })
        except (OSError, ValueError):
            pass
        if not any(
            existing.get("file_path") == captured["file_path"]
            and existing.get("sha256") == captured["sha256"]
            for existing in self.source_documents
        ):
            self.source_documents.append(captured)

    def update_from_observation(self, tool_name: str, data: Any, step_id: Optional[int] = None):
        """Intelligently inspect tool output and store relevant facts."""
        if step_id is not None:
            self.step_results[step_id] = data

        if not data:
            return

        # If data is a string (e.g. read_document)
        if isinstance(data, str):
            self.extracted_data[f"raw_text_{step_id or len(self.extracted_data)}"] = data
            self.add_note(f"Loaded document text ({len(data)} characters).")
            return

        # If data is a list of items (e.g. search_files, erp_list_invoices)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "path" in item:
                    if item["path"] not in self.files_found:
                        self.files_found.append(item["path"])
            if self.files_found:
                self.record_entity("file_path", self.files_found[0])
                self.record_entity("latest_file_path", self.files_found[0])
                if isinstance(data[0], dict) and "filename" in data[0]:
                    self.record_entity("filename", data[0]["filename"])
            self.add_note(f"Storage search located {len(data)} file(s).")
            return

        if not isinstance(data, dict):
            return

        for document in data.get("source_documents", []):
            self.add_source_document(document)
        if "deal_record" in data:
            deal = data["deal_record"]
            self.extracted_data["deal_record"] = dict(deal)
            for key in ("deal_id", "signed_at"):
                self.record_entity(key, deal[key])
            self.record_entity("customer_name", deal["customer"])
            self.add_note(f"Selected signed deal {deal['deal_id']} for {deal['customer']} ({deal['signed_at']}).")
        if "selection_manifest" in data:
            self.extracted_data["deal_selection_manifest"] = data["selection_manifest"]
            self.extracted_data["deal_customer_query"] = data.get("customer_query", "")
            self.add_note(f"Compared {data['eligible_count']} eligible signed deal(s) by source signing date; drafts were excluded.")
        if "quotation_record" in data:
            quote = data["quotation_record"]
            self.extracted_data["quotation_record"] = dict(quote)
            self.record_entity("quotation_id", quote["quotation_id"])
            self.record_entity("quotation_amount", quote["amount"])
            self.record_entity("quotation_currency", quote["currency"])
            self.record_entity("quote_valid_until", quote["valid_until"])
            self.add_note(f"Read linked quotation {quote['quotation_id']} and checked its deal reference, customer, amount, and currency.")
        if tool_name == "search_company_records":
            self.extracted_data["company_search"] = data
            self.record_entity("matched_resources", data["total_matches"])
            self.record_entity("searched_term", data["query"])
            self.record_entity("search_no_results", not data["matches"] and not data.get("skipped_files"))
            for match in data["matches"]:
                if match.get("file_path"):
                    document = {"file_path": match["file_path"], "sha256": match["sha256"]}
                    self.add_source_document(document)
            self.add_note(f"Searched company document contents, ledger invoices, and vendors for '{data['query']}': {data['total_matches']} match(es).")

        if data.get("file_path") and data.get("sha256"):
            document = {"file_path": data["file_path"], "sha256": data["sha256"]}
            self.add_source_document(document)
            self.record_entity("file_path", data["file_path"])
            f_name = Path(data["file_path"]).name
            self.add_note(f"Verified source document '{f_name}' (SHA-256: {data['sha256'][:12]}...).")
        if data.get("content"):
            c_val = data["content"]
            self.extracted_data[f"document_content_{step_id or len(self.extracted_data)}"] = c_val
            self.record_entity("content", c_val)
            self.record_entity("document_content", c_val)
            self.record_entity("invoice_content", c_val)
            self.record_entity("file_content", c_val)
            self.record_entity("text", c_val)
        if "vendor_data" in data:
            self.extracted_data["vendor_profile"] = data["vendor_data"]
            self.extracted_data["vendor_info"] = data["vendor_data"]
            for key, value in data["vendor_data"].items():
                self.record_entity("vendor_name" if key == "name" else key, value)
            v_name = data["vendor_data"].get("name", "Vendor")
            t_id = data["vendor_data"].get("tax_id", "N/A")
            self.add_note(f"Parsed vendor profile for '{v_name}' (Tax ID: {t_id}).")

        # If an invoice file was found or parsed
        if "invoice_data" in data:
            inv = data["invoice_data"]
            self.extracted_data["latest_invoice"] = inv
            self.extracted_data["invoice_data"] = inv
            if inv.get("invoice_number"):
                self.record_entity("invoice_number", inv["invoice_number"])
            if inv.get("amount"):
                self.record_entity("amount", inv["amount"])
            if inv.get("due_date"):
                self.record_entity("due_date", inv["due_date"])
            if inv.get("vendor"):
                self.record_entity("vendor_name", inv["vendor"])
            if "file_path" in data:
                self.files_found.append(data["file_path"])
                self.record_entity("file_path", data["file_path"])
            elif "latest_file_path" in data:
                self.files_found.append(data["latest_file_path"])
                self.record_entity("file_path", data["latest_file_path"])
            self.add_note(
                f"Discovered invoice #{inv.get('invoice_number', 'N/A')} from {inv.get('vendor', 'vendor')} "
                f"for ${inv.get('amount', 'N/A')} due {inv.get('due_date', 'N/A')}."
            )

        # If direct invoice extraction
        if "amount" in data and "due_date" in data:
            if tool_name == "extract_invoice_data":
                self.extracted_data["invoice_source"] = dict(data)
                self.extracted_data["invoice_data"] = dict(data)
            if data.get("invoice_number"):
                self.record_entity("invoice_number", data["invoice_number"])
            self.record_entity("amount", data["amount"])
            self.record_entity("due_date", data["due_date"])
            if data.get("vendor"):
                self.record_entity("vendor_name", data["vendor"])
            self.add_note(
                f"Extracted invoice fields: #{data.get('invoice_number', 'N/A')} | "
                f"Amount: ${data.get('amount', 'N/A')} | Due: {data.get('due_date', 'N/A')}."
            )

        # If vendor was looked up
        if "vendor_id" in data:
            self.extracted_data["vendor_info"] = dict(data)
            self.record_entity("vendor_id", data["vendor_id"])
            if "name" in data:
                self.record_entity("vendor_name", data["name"])
            self.add_note(f"ERP Vendor Lookup: Matched '{data.get('name', 'vendor')}' to Vendor ID: {data['vendor_id']}.")

        # If invoice was created
        if tool_name == "erp_create_invoice" and "invoice_number" in data:
            self.record_entity("created_invoice_number", data["invoice_number"])
            self.record_entity("created_invoice_record", data)
            self.add_note(f"ERP Ledger Action: Created invoice #{data['invoice_number']} for ${data.get('amount', 'N/A')} under Vendor ID {data.get('vendor_id', 'N/A')}.")

    def interpolate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dynamically resolve placeholders in tool arguments using working memory."""
        interpolated = {}
        for k, v in args.items():
            if isinstance(v, str) and "{{" in v and "}}" in v:
                val = None
                # Pattern 1: {{step_1_result.field}} or {{step_1.field}}
                m1 = re.search(r"\{\{step_(\d+)(?:_result)?\.([A-Za-z0-9_]+)\}\}", v)
                if m1:
                    s_id = int(m1.group(1))
                    field = m1.group(2)
                    res = self.step_results.get(s_id) or self.step_results.get(str(s_id))
                    if isinstance(res, dict):
                        val = res.get(field)
                        if val is None and field == "file_path":
                            val = res.get("latest_file_path")
                        elif val is None and field == "content":
                            val = res.get("text") or res.get("content")
                    elif isinstance(res, str) and field == "content":
                        val = res
                    if val is None:
                        val = self.entities.get(field)

                # Pattern 2: {{field_from_step_1}}
                if val is None:
                    m2 = re.search(r"\{\{([A-Za-z0-9_]+)_from_step_(\d+)\}\}", v)
                    if m2:
                        field = m2.group(1)
                        s_id = int(m2.group(2))
                        res = self.step_results.get(s_id) or self.step_results.get(str(s_id))
                        if isinstance(res, dict):
                            val = res.get(field)
                        if val is None:
                            val = self.entities.get(field)

                # Pattern 3: Generic or dotted reference e.g. {{invoice_data.amount}}, {{vendor_id}}
                if val is None:
                    var_name = v.strip("{} ").replace("scratchpad.", "")
                    # Dotted expression: {{output_ref.field}} or {{latest_invoice.file_path}}
                    if "." in var_name:
                        ref_name, field_name = var_name.split(".", 1)
                        val = self.get_entity(field_name)
                        if val is None and ref_name in self.extracted_data and isinstance(self.extracted_data[ref_name], dict):
                            val = self.extracted_data[ref_name].get(field_name)
                    if val is None:
                        val = self.get_entity(var_name)
                    if val is None:
                        clean_var = re.sub(r"(_from)?_step_\d+", "", var_name)
                        clean_var = re.sub(r"^step_\d+_", "", clean_var)
                        val = self.get_entity(clean_var)
                    if val is None and any(w in var_name.lower() for w in ("content", "text")):
                        val = self.get_entity("content") or self.get_entity("invoice_content") or self.get_entity("document_content")
                    if val is None and ("file" in var_name.lower() or "path" in var_name.lower()):
                        val = self.get_entity("file_path") or self.get_entity("latest_file_path")
                    if val is None:
                        for ek, ev in self.entities.items():
                            if ek.lower() in var_name.lower() or var_name.lower() in ek.lower():
                                val = ev
                                break


                # Fallback to key itself if still unresolved but present in entities
                if val is None and k in self.entities:
                    val = self.entities[k]

                interpolated[k] = val if val is not None else v
            elif v is None or v == "":
                # Fallback to matching entity if present
                if k in self.entities:
                    interpolated[k] = self.entities[k]
                else:
                    interpolated[k] = v
            else:
                # Also check if placeholder-like string or missing vendor/amount
                if str(v).startswith("{{") and k in self.entities:
                    interpolated[k] = self.entities[k]
                elif k == "vendor_id" and "vendor_id" in self.entities and (not v or v == "VND-???" or str(v).startswith("{{")):
                    interpolated[k] = self.entities["vendor_id"]
                elif k == "amount" and "amount" in self.entities and (not v or v == 0.0 or str(v).startswith("{{")):
                    interpolated[k] = self.entities["amount"]
                elif k == "due_date" and "due_date" in self.entities and (not v or v == "" or str(v).startswith("{{")):
                    interpolated[k] = self.entities["due_date"]
                elif k == "invoice_number" and "invoice_number" in self.entities and (not v or v == "" or str(v).startswith("{{")):
                    interpolated[k] = self.entities["invoice_number"]
                else:
                    interpolated[k] = v
        return interpolated

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": self.entities,
            "extracted_data": self.extracted_data,
            "files_found": self.files_found,
            "step_results": self.step_results,
            "notes": self.notes,
            "source_documents": self.source_documents,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scratchpad":
        raw_sr = data.get("step_results", {})
        sr = {}
        for k, v in raw_sr.items():
            try:
                sr[int(k)] = v
            except Exception:
                sr[k] = v
                
        return cls(
            entities=data.get("entities", {}),
            extracted_data=data.get("extracted_data", {}),
            files_found=data.get("files_found", []),
            step_results=sr,
            notes=data.get("notes", []),
            source_documents=data.get("source_documents", []),
        )
