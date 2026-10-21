"""Context Working Memory and Scratchpad for Operon.

Maintains discovered entities, cross-step state, extracted parameters,
and allows dynamic reference interpolation between execution steps.
"""

from typing import Dict, Any, List, Optional
import re
from pydantic import BaseModel, Field

class Scratchpad(BaseModel):
    """Working memory tracking information discovered during agent execution."""
    entities: Dict[str, Any] = Field(default_factory=dict, description="Named entities e.g. vendor_id, invoice_number")
    extracted_data: Dict[str, Any] = Field(default_factory=dict, description="Raw extracted structures")
    files_found: List[str] = Field(default_factory=list, description="Discovered file paths")
    step_results: Dict[int, Any] = Field(default_factory=dict, description="Results indexed by step_id")
    notes: List[str] = Field(default_factory=list, description="Reasoning notes accumulated during task")

    def record_entity(self, key: str, value: Any):
        """Store an entity in working memory."""
        self.entities[key] = value

    def get_entity(self, key: str, default: Any = None) -> Any:
        """Retrieve an entity from working memory."""
        return self.entities.get(key, default)

    def update_from_observation(self, tool_name: str, data: Any, step_id: Optional[int] = None):
        """Intelligently inspect tool output and store relevant facts."""
        if step_id is not None:
            self.step_results[step_id] = data

        if not data:
            return

        # If data is a string (e.g. read_document)
        if isinstance(data, str):
            self.extracted_data[f"raw_text_{step_id or len(self.extracted_data)}"] = data
            return

        if not isinstance(data, dict):
            return

        # If an invoice file was found or parsed
        if "invoice_data" in data:
            inv = data["invoice_data"]
            self.extracted_data["latest_invoice"] = inv
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

        # If direct invoice extraction
        if "amount" in data and "due_date" in data:
            if data.get("invoice_number"):
                self.record_entity("invoice_number", data["invoice_number"])
            self.record_entity("amount", data["amount"])
            self.record_entity("due_date", data["due_date"])
            if data.get("vendor"):
                self.record_entity("vendor_name", data["vendor"])

        # If vendor was looked up
        if "vendor_id" in data:
            self.record_entity("vendor_id", data["vendor_id"])
            if "name" in data:
                self.record_entity("vendor_name", data["name"])

        # If invoice was created
        if tool_name == "erp_create_invoice" and "invoice_number" in data:
            self.record_entity("created_invoice_number", data["invoice_number"])
            self.record_entity("created_invoice_record", data)

    def interpolate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dynamically resolve placeholders in tool arguments using working memory."""
        interpolated = {}
        for k, v in args.items():
            if isinstance(v, str) and "{{" in v and "}}" in v:
                # Handle references like {{step_1_result.file_path}}
                step_m = re.search(r"\{\{step_(\d+)_result\.([A-Za-z0-9_]+)\}\}", v)
                if step_m:
                    s_id = int(step_m.group(1))
                    field = step_m.group(2)
                    res = self.step_results.get(s_id) or self.step_results.get(str(s_id))
                    val = None
                    if isinstance(res, dict):
                        val = res.get(field)
                        if val is None and field == "file_path":
                            val = res.get("latest_file_path")
                        elif val is None and field == "content":
                            val = res.get("text") or res.get("content")
                    elif isinstance(res, str) and field == "content":
                        val = res
                        
                    # If not in step_results, check top-level entities
                    if val is None:
                        val = self.entities.get(field)
                        
                    interpolated[k] = val if val is not None else v
                else:
                    # Generic entity reference {{entity_name}}
                    var_name = v.strip("{} ").replace("scratchpad.", "")
                    interpolated[k] = self.get_entity(var_name, v)
            elif v is None or v == "":
                # Fallback to matching entity if present
                if k in self.entities:
                    interpolated[k] = self.entities[k]
                else:
                    interpolated[k] = v
            else:
                # Also check if value can be updated if entity was found (e.g. dynamic amount or vendor_id)
                if k == "vendor_id" and "vendor_id" in self.entities and (not v or v == "VND-???"):
                    interpolated[k] = self.entities["vendor_id"]
                elif k == "amount" and "amount" in self.entities and (not v or v == 0.0):
                    interpolated[k] = self.entities["amount"]
                elif k == "due_date" and "due_date" in self.entities and (not v or v == ""):
                    interpolated[k] = self.entities["due_date"]
                elif k == "invoice_number" and "invoice_number" in self.entities and (not v or v == ""):
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
            "notes": self.notes
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
            notes=data.get("notes", [])
        )
