"""A genuine validation failure followed by date normalization and verification."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from operon.config import settings
from operon.llm import llm_provider
from cli import run_task


def run_recovery_demo():
    previous_dir, previous_client = settings.sample_data_dir, llm_provider._client
    try:
        with TemporaryDirectory(prefix="operon-recovery-") as directory:
            root = Path(directory)
            (root / "invoices").mkdir()
            (root / "invoices" / "company_x_recovery.json").write_text(json.dumps({
                "invoice_number": "INV-RECOVERY-001", "vendor": "Company X Solutions",
                "invoice_date": "2026-03-10", "due_date": "Due: 2026-04-10 end of business",
                "amount": "$13,446.00", "currency": "USD",
            }), encoding="utf-8")
            settings.sample_data_dir, llm_provider._client = root, None
            packet = run_task("Find the latest invoice from Company X, enter it into ERP and verify.")
            assert packet.status == "completed"
            assert any(error.recovery_strategy for error in packet.errors)
            print("Recovery confirmed: an invalid date failed, was normalized, and passed source verification.")
    finally:
        settings.sample_data_dir, llm_provider._client = previous_dir, previous_client


if __name__ == "__main__":
    run_recovery_demo()
