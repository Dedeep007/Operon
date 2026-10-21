"""LLM Factory and Model Interface for Operon.

Integrates with Groq API using Alibaba Qwen 3.8 27B ('qwen/qwen3.8-27b'),
with an intelligent simulation fallback when GROQ_API_KEY is not provided.
"""

import os
import json
from typing import Optional, Any, Dict, List
from operon.config import settings

class LLMProvider:
    """Provides LLM client and helper methods for structured reasoning."""
    
    def __init__(self):
        self._client = None
        self._is_live = False
        self._init_client()

    def _init_client(self):
        api_key = settings.groq_api_key or os.getenv("GROQ_API_KEY")
        if api_key and api_key.strip() and not api_key.startswith("your_"):
            try:
                from langchain_groq import ChatGroq
                self._client = ChatGroq(
                    model=settings.model_name,
                    api_key=api_key.strip(),
                    temperature=settings.temperature,
                    max_retries=2
                )
                self._is_live = True
                print(f"[Operon] Initialized Live Groq Engine with model: {settings.model_name}")
            except Exception as e:
                print(f"[Operon] Warning: Failed to initialize ChatGroq: {e}. Falling back to simulation mode.")
                self._client = None
                self._is_live = False
        else:
            self._client = None
            self._is_live = False

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def model_name(self) -> str:
        return settings.model_name if self._is_live else f"{settings.model_name} (Simulation Engine)"

    def invoke(self, messages: List[Any]) -> str:
        """Invoke the LLM or simulation fallback."""
        if self._is_live and self._client:
            try:
                response = self._client.invoke(messages)
                return response.content
            except Exception as e:
                print(f"[Operon] Live Groq call error: {e}. Falling back to simulation logic.")
        return self._fallback_invoke(messages)

    def _fallback_invoke(self, messages: List[Any]) -> str:
        """Deterministic, grounded simulation of Qwen 3.8 27B reasoning."""
        # Convert messages to text
        combined = " ".join([str(m) for m in messages]).lower()
        
        # Scenario: Planning for finding latest invoice from Company X
        if "company x" in combined and "invoice" in combined:
            return json.dumps({
                "thought": "The user wants to find the latest invoice from Company X, extract amount and due date, enter it into our internal ERP, and verify completion.",
                "steps": [
                    {
                        "step_id": 1,
                        "description": "Locate and identify the latest invoice file for Company X",
                        "tool_name": "find_latest_invoice_file",
                        "tool_args": {"company_name": "Company X"},
                        "expected_outcome": "Path and parsed details of the most recent invoice"
                    },
                    {
                        "step_id": 2,
                        "description": "Query internal ERP to retrieve the registered Vendor ID for Company X",
                        "tool_name": "erp_lookup_vendor",
                        "tool_args": {"query": "Company X"},
                        "expected_outcome": "Vendor record with vendor_id"
                    },
                    {
                        "step_id": 3,
                        "description": "Enter the extracted invoice amount and due date into the internal ERP",
                        "tool_name": "erp_create_invoice",
                        "tool_args": {
                            "invoice_number": "INV-X-2026-003",
                            "vendor_id": "VND-001",
                            "amount": 13446.00,
                            "due_date": "2026-04-10"
                        },
                        "expected_outcome": "Invoice record created in internal accounting system"
                    },
                    {
                        "step_id": 4,
                        "description": "Independently verify invoice status in the ERP ledger",
                        "tool_name": "erp_verify_invoice_status",
                        "tool_args": {
                            "invoice_number": "INV-X-2026-003",
                            "expected_amount": 13446.00,
                            "expected_due_date": "2026-04-10"
                        },
                        "expected_outcome": "Ledger confirmation that invoice exists with correct amount and due date"
                    }
                ]
            })

        # Scenario: Vendor onboarding generalization
        if "vendor" in combined or "onboard" in combined or "apex" in combined:
            return json.dumps({
                "thought": "The goal is to read vendor onboarding info and register them into the internal ERP.",
                "steps": [
                    {
                        "step_id": 1,
                        "description": "Read new vendor onboarding document",
                        "tool_name": "read_document",
                        "tool_args": {"file_path": str(settings.sample_data_dir / "vendors" / "new_vendor_apex_tech.json")},
                        "expected_outcome": "Vendor profile details"
                    },
                    {
                        "step_id": 2,
                        "description": "Register vendor into internal ERP system",
                        "tool_name": "erp_register_vendor",
                        "tool_args": {
                            "name": "Apex Technologies LLC",
                            "tax_id": "TX-44819-APX",
                            "payment_terms": "Net 30",
                            "contact_email": "contracts@apextech.example.com"
                        },
                        "expected_outcome": "New vendor created with active status"
                    }
                ]
            })

        # Generic default plan
        return json.dumps({
            "thought": "Analyze user task and decompose into file search and ERP inspection.",
            "steps": [
                {
                    "step_id": 1,
                    "description": "Search available data directories for relevant records",
                    "tool_name": "search_files",
                    "tool_args": {"pattern": "*"},
                    "expected_outcome": "List of matching enterprise files"
                }
            ]
        })

# Global LLM instance
llm_provider = LLMProvider()
