"""Simulated Enterprise Resource Planning (ERP) & Accounting System.

Provides an in-memory ledger with business validation, audit records, and state
inspection. The dashboard serializes tasks; this is not a transactional database.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from copy import deepcopy
import json
import re

class ERPValidationError(Exception):
    """Raised when data submitted to the ERP violates schema or business rules."""
    pass

class ERPNotFoundError(Exception):
    """Raised when a requested resource does not exist in the ERP."""
    pass

class ERPSystem:
    """Simulated Enterprise Accounting & Vendor Management System."""
    
    def __init__(self):
        self.vendors: Dict[str, Dict[str, Any]] = {}
        self.invoices: Dict[str, Dict[str, Any]] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self._seed_initial_data()
        self._initial_snapshot = self.get_state_snapshot()
    
    def _seed_initial_data(self):
        """Seed pre-existing vendors and past records."""
        self.audit_log = []
        self.vendors = {
            "VND-001": {
                "vendor_id": "VND-001",
                "name": "Company X Solutions",
                "alias": ["Company X", "Co X", "CompanyX"],
                "tax_id": "TX-99214-X",
                "status": "Active",
                "payment_terms": "Net 30",
                "contact_email": "billing@companyx.example.com",
                "balance_owed": 0.0
            },
            "VND-002": {
                "vendor_id": "VND-002",
                "name": "Acme Logistics Inc",
                "alias": ["Acme", "Acme Corp"],
                "tax_id": "TX-11884-A",
                "status": "Active",
                "payment_terms": "Net 15",
                "contact_email": "accounts@acme.example.com",
                "balance_owed": 1200.00
            },
            "VND-003": {
                "vendor_id": "VND-003",
                "name": "Globex Software Technologies",
                "alias": ["Globex", "Globex Corp", "Globex Software"],
                "tax_id": "TX-55412-G",
                "status": "Active",
                "payment_terms": "Net 60",
                "contact_email": "finance@globex.example.com",
                "balance_owed": 3200.00
            },
            "VND-004": {
                "vendor_id": "VND-004",
                "name": "OmniCorp Industries",
                "alias": ["OmniCorp", "Omni Corp"],
                "tax_id": "TX-77301-OMN",
                "status": "Active",
                "payment_terms": "Net 45",
                "contact_email": "enterprise-billing@omnicorp.example.com",
                "balance_owed": 0.0
            }
        }
        
        # Pre-seed realistic past records for multiple vendors
        self.invoices = {
            "INV-X-2026-001": {
                "invoice_number": "INV-X-2026-001",
                "vendor_id": "VND-001",
                "vendor_name": "Company X Solutions",
                "amount": 4500.00,
                "due_date": "2026-02-15",
                "status": "PAID",
                "created_at": "2026-01-16T10:00:00",
                "source": "manual_entry"
            },
            "INV-ACM-2026-001": {
                "invoice_number": "INV-ACM-2026-001",
                "vendor_id": "VND-002",
                "vendor_name": "Acme Logistics Inc",
                "amount": 8750.00,
                "due_date": "2026-03-15",
                "status": "PAID",
                "created_at": "2026-02-13T09:30:00",
                "source": "manual_entry"
            },
            "INV-GLX-2026-001": {
                "invoice_number": "INV-GLX-2026-001",
                "vendor_id": "VND-003",
                "vendor_name": "Globex Software Technologies",
                "amount": 3200.00,
                "due_date": "2026-03-31",
                "status": "PENDING",
                "created_at": "2026-02-01T14:15:00",
                "source": "manual_entry"
            }
        }

    def _log_audit(self, action: str, details: Dict[str, Any]):
        """Capture an independent copy of action details in the local audit log."""
        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": deepcopy(details)
        })

    def find_vendor(self, query: str) -> Optional[Dict[str, Any]]:
        """Look up a vendor by ID, exact name, or alias."""
        clean_q = query.strip().lower()
        if not clean_q:
            return None
        
        # Check by ID
        for vid, v in self.vendors.items():
            if vid.lower() == clean_q:
                self._log_audit("FIND_VENDOR_SUCCESS", {"query": query, "vendor_id": vid})
                return deepcopy(v)
                
        # Check by Name or Aliases
        for vid, v in self.vendors.items():
            if v["name"].lower() == clean_q or any(alias.lower() == clean_q for alias in v.get("alias", [])):
                self._log_audit("FIND_VENDOR_SUCCESS", {"query": query, "vendor_id": vid})
                return deepcopy(v)
                
        # Substring search
        for vid, v in self.vendors.items():
            if clean_q in v["name"].lower() or any(clean_q in alias.lower() for alias in v.get("alias", [])):
                self._log_audit("FIND_VENDOR_SUCCESS", {"query": query, "vendor_id": vid})
                return deepcopy(v)
                
        self._log_audit("FIND_VENDOR_NOT_FOUND", {"query": query})
        return None

    def register_vendor(self, name: str, tax_id: str, payment_terms: str = "Net 30", contact_email: str = "") -> Dict[str, Any]:
        """Register a new vendor in the system."""
        if not name or not tax_id:
            raise ERPValidationError("Vendor name and tax_id are required.")
        name, tax_id = name.strip(), tax_id.strip()
        if not name or not tax_id:
            raise ERPValidationError("Vendor name and tax_id are required.")
        for vendor in self.vendors.values():
            if vendor["tax_id"].casefold() == tax_id.casefold() or vendor["name"].casefold() == name.casefold():
                fields = {"name": name, "tax_id": tax_id, "payment_terms": payment_terms, "contact_email": contact_email.strip()}
                if all(str(vendor[k]).casefold() == str(v).casefold() for k, v in fields.items()):
                    return deepcopy(vendor)
                raise ERPValidationError("DuplicateVendorError: A vendor with this name or tax ID has conflicting details.")
            
        new_id = f"VND-{len(self.vendors) + 1:03d}"
        vendor_data = {
            "vendor_id": new_id,
            "name": name.strip(),
            "alias": [name.strip()],
            "tax_id": tax_id.strip(),
            "status": "Active",
            "payment_terms": payment_terms,
            "contact_email": contact_email.strip(),
            "balance_owed": 0.0
        }
        self.vendors[new_id] = vendor_data
        self._log_audit("REGISTER_VENDOR", {"vendor_id": new_id, "name": name})
        return dict(vendor_data)

    def create_invoice(self, invoice_number: str, vendor_id: str, amount: float, due_date: str) -> Dict[str, Any]:
        """Enter a new invoice into the ERP ledger.
        
        Validations:
        - invoice_number must be non-empty and unique
        - vendor_id must exist
        - amount must be a positive float
        - due_date must be in YYYY-MM-DD format
        """
        if not invoice_number or not invoice_number.strip():
            raise ERPValidationError("Invoice number is required.")
            
        clean_inv_num = invoice_number.strip().upper()
        if clean_inv_num in self.invoices:
            raise ERPValidationError(f"DuplicateInvoiceError: Invoice '{clean_inv_num}' is already registered in the system.")
            
        if vendor_id not in self.vendors:
            raise ERPNotFoundError(f"VendorNotFoundError: Vendor ID '{vendor_id}' is not registered in the ERP.")
            
        try:
            val_amount = float(amount)
            from operon.validation import parse_amount
            val_amount = parse_amount(amount)
        except Exception:
            raise ERPValidationError(f"InvalidAmountError: Amount '{amount}' must be a positive number.")
            
        # Validate date format YYYY-MM-DD
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(due_date)):
            raise ERPValidationError(f"InvalidDateFormatError: Due date '{due_date}' must follow ISO format YYYY-MM-DD.")
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            raise ERPValidationError(f"InvalidDateFormatError: Due date '{due_date}' is not a calendar date.")
            
        vendor = self.vendors[vendor_id]
        new_record = {
            "invoice_number": clean_inv_num,
            "vendor_id": vendor_id,
            "vendor_name": vendor["name"],
            "amount": round(val_amount, 2),
            "due_date": due_date,
            "status": "PENDING",
            "created_at": datetime.now().isoformat(),
            "source": "autonomous_worker"
        }
        
        self.invoices[clean_inv_num] = new_record
        vendor["balance_owed"] = round(vendor["balance_owed"] + val_amount, 2)
        
        self._log_audit("CREATE_INVOICE", new_record)
        return dict(new_record)

    def get_invoice(self, invoice_number: str) -> Optional[Dict[str, Any]]:
        """Retrieve an invoice by number."""
        clean_num = invoice_number.strip().upper()
        inv = self.invoices.get(clean_num)
        if inv:
            self._log_audit("GET_INVOICE_SUCCESS", {"invoice_number": clean_num})
            return dict(inv)
        self._log_audit("GET_INVOICE_NOT_FOUND", {"invoice_number": clean_num})
        return None

    def list_invoices(self, vendor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all invoices or filter by vendor."""
        results = deepcopy(list(self.invoices.values()))
        if vendor_id:
            results = [inv for inv in results if inv["vendor_id"] == vendor_id]
        return results

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Capture entire current state for diffing and audit verification."""
        return {
            "vendor_count": len(self.vendors),
            "invoice_count": len(self.invoices),
            "invoices": deepcopy(self.invoices),
            "vendors": deepcopy(self.vendors)
        }

    def compute_state_diff(self, baseline=None, audit_start: int = 0) -> Dict[str, Any]:
        """Compute differences between initial state and current state."""
        current = self.get_state_snapshot()
        baseline = baseline if baseline is not None else self._initial_snapshot
        initial_inv = baseline.get("invoices", {})
        current_inv = current.get("invoices", {})
        
        new_invoices = [inv for k, inv in current_inv.items() if k not in initial_inv]
        new_vendors = [v for k, v in current["vendors"].items() if k not in baseline.get("vendors", {})]
        return {
            "new_invoices_created": new_invoices,
            "total_new_invoices": len(new_invoices),
            "new_vendors_created": new_vendors,
            "total_new_vendors": len(new_vendors),
            "vendor_balance_changes": [
                {"vendor_id": k, "before": baseline["vendors"][k]["balance_owed"], "after": v["balance_owed"]}
                for k, v in current["vendors"].items()
                if k in baseline.get("vendors", {}) and v["balance_owed"] != baseline["vendors"][k]["balance_owed"]
            ],
            "audit_events_count": len(self.audit_log) - audit_start
        }

    def clone(self):
        """Create an independent sandbox from the current ledger."""
        sandbox = ERPSystem()
        snapshot = self.get_state_snapshot()
        sandbox.invoices = snapshot["invoices"]
        sandbox.vendors = snapshot["vendors"]
        sandbox.audit_log = []
        sandbox._initial_snapshot = sandbox.get_state_snapshot()
        return sandbox

    def reset(self):
        self._seed_initial_data()
        self._initial_snapshot = self.get_state_snapshot()

# Global singleton simulated ERP instance
default_erp = ERPSystem()
