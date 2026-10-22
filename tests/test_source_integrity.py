"""Source identity, chronological selection, and independent audit regressions."""

import json
from operon.agent import OperonAgent
from operon.config import settings
from operon.environment.erp_system import ERPSystem
from operon.llm import llm_provider
from operon.tools.file_tools import find_latest_invoice_file
from operon.tools.registry import registry


def write_invoice(path, company, number, issued):
    path.write_text(json.dumps({"invoice_number": number, "vendor": company,
        "invoice_date": issued, "amount": 500, "due_date": "2026-12-01"}), encoding="utf-8")


def test_company_x_does_not_match_company_y(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sample_data_dir", tmp_path)
    write_invoice(tmp_path / "company_x.json", "Company X Solutions", "INV-X-1", "2026-02-01")
    write_invoice(tmp_path / "company_y.json", "Company Y Solutions", "INV-Y-2", "2026-10-01")
    result = find_latest_invoice_file("Company X", directory=str(tmp_path))
    assert result["invoice_data"]["invoice_number"] == "INV-X-1"


def test_latest_uses_all_matching_source_dates_not_filename_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sample_data_dir", tmp_path)
    write_invoice(tmp_path / "company_x.json", "Company X Solutions", "INV-X-1", "2026-02-01")
    write_invoice(tmp_path / "unrelated_filename.json", "Company X Solutions", "INV-X-2", "2026-10-01")
    assert find_latest_invoice_file("Company X", directory=str(tmp_path))["invoice_data"]["invoice_number"] == "INV-X-2"


def test_source_change_during_execution_is_detected(tmp_path, monkeypatch):
    directory = tmp_path / "invoices"
    directory.mkdir()
    path = directory / "company_x.json"
    write_invoice(path, "Company X Solutions", "INV-CHANGED-1", "2026-10-01")
    monkeypatch.setattr(settings, "sample_data_dir", tmp_path)
    original = registry._tools["erp_create_invoice"]
    def change_source(**args):
        result = original(**args)
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return result
    monkeypatch.setitem(registry._tools, "erp_create_invoice", change_source)
    packet = OperonAgent(erp=ERPSystem()).run("Process the latest invoice from Company X and verify.")
    assert packet.status == "partially_completed"
    assert "A source document changed during execution." in packet.verification.discrepancies


def test_wrong_vendor_is_detected_even_when_amount_and_date_match(monkeypatch):
    original = registry._tools["erp_create_invoice"]
    monkeypatch.setitem(registry._tools, "erp_create_invoice", lambda **args: original(**{**args, "vendor_id": "VND-002"}))
    packet = OperonAgent(erp=ERPSystem()).run("Process the latest invoice from Company X and verify.")
    assert not packet.verification.is_verified
    assert any("Vendor mismatch" in d for d in packet.verification.discrepancies)


def test_unavailable_live_model_is_disclosed_in_report(monkeypatch):
    class Unavailable:
        def invoke(self, messages):
            raise RuntimeError("Unavailable")
    monkeypatch.setattr(llm_provider, "_client", Unavailable())
    packet = OperonAgent(erp=ERPSystem()).run("Process the latest invoice from Company X and verify.")
    assert packet.status == "completed"
    assert packet.planner_backend == "offline (Groq unavailable)"
