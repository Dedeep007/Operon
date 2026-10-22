"""Resource classification, path boundaries, and approval-safe argument display."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from operon.config import settings


POLICY_VERSION = "resource-policy-2026-10-22-v1"
Sensitivity = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
ApprovalScope = Literal["execution", "all_modes"]


class ResourceClassification(BaseModel):
    """A policy label attached to a file or data-bearing action."""

    policy_id: str
    resource: str
    data_classification: Sensitivity
    data_categories: list[str] = Field(default_factory=list)
    reason: str
    requires_approval: bool = False
    approval_scope: ApprovalScope = "execution"


_DIRECTORY_RULES = {
    "vendors": (
        "RESTRICTED",
        ["tax identifier", "business contact"],
        "Vendor onboarding profiles contain identifiers and contact details.",
        True,
    ),
    "invoices": (
        "CONFIDENTIAL",
        ["financial record", "billing details"],
        "Invoices contain non-public financial and billing information.",
        False,
    ),
    "deals": (
        "CONFIDENTIAL",
        ["commercial terms", "customer relationship"],
        "Deal records contain non-public commercial information.",
        False,
    ),
    "quotations": (
        "CONFIDENTIAL",
        ["pricing", "commercial terms"],
        "Quotations contain non-public pricing and commercial terms.",
        False,
    ),
    "blueprints": (
        "CONFIDENTIAL",
        ["proprietary design"],
        "Blueprints contain proprietary technical information.",
        False,
    ),
    "documents": (
        "INTERNAL",
        ["company document"],
        "This file belongs to the internal company workspace.",
        False,
    ),
}

_RESTRICTED_HINTS = re.compile(
    r"(?:credential|password|secret|api[_-]?key|payroll|employee|hr[_-]|tax[_-]?id|bank[_-]?account|pii)",
    re.I,
)
_CONFIDENTIAL_HINTS = re.compile(
    r"(?:invoice|quotation|quote|deal|contract|blueprint|purchase[_-]?order)",
    re.I,
)


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def allowed_read_roots() -> list[Path]:
    return [settings.sample_data_dir.resolve(), settings.storage_dir.resolve()]


def allowed_write_roots() -> list[Path]:
    return [settings.storage_dir.resolve(), Path(tempfile.gettempdir()).resolve()]


def enforce_resource_scope(path: str | Path, *, operation: Literal["read", "write"] = "read") -> Path:
    """Resolve a path and reject access outside the configured sandbox roots."""

    resolved = Path(path).expanduser().resolve()
    roots = allowed_read_roots() if operation == "read" else allowed_write_roots()
    if not any(_within(resolved, root) for root in roots):
        names = ", ".join(str(root) for root in roots)
        raise PermissionError(
            f"ResourceScopeError: {operation.title()} access to '{resolved}' is outside the allowed sandbox roots: {names}."
        )
    return resolved


def classify_resource(path: str | Path) -> ResourceClassification:
    """Classify a resource from its sandbox location and conservative name hints."""

    resolved = Path(path).expanduser().resolve()
    sample_root = settings.sample_data_dir.resolve()
    storage_root = settings.storage_dir.resolve()
    resource = str(resolved)

    if _within(resolved, sample_root):
        relative = resolved.relative_to(sample_root)
        group = relative.parts[0].casefold() if relative.parts else ""
        if group in _DIRECTORY_RULES:
            level, categories, reason, approval = _DIRECTORY_RULES[group]
            return ResourceClassification(
                policy_id=f"{POLICY_VERSION}:{group}",
                resource=str(relative).replace("\\", "/"),
                data_classification=level,
                data_categories=categories,
                reason=reason,
                requires_approval=approval,
                approval_scope="all_modes" if approval else "execution",
            )
        label = str(relative).replace("\\", "/")
    elif _within(resolved, storage_root):
        label = str(resolved.relative_to(storage_root)).replace("\\", "/")
    else:
        return ResourceClassification(
            policy_id=f"{POLICY_VERSION}:outside-sandbox",
            resource=resource,
            data_classification="RESTRICTED",
            data_categories=["unscoped local resource"],
            reason="The resource is outside Operon’s approved company sandbox.",
            requires_approval=True,
            approval_scope="all_modes",
        )

    if _RESTRICTED_HINTS.search(label):
        return ResourceClassification(
            policy_id=f"{POLICY_VERSION}:restricted-name",
            resource=label,
            data_classification="RESTRICTED",
            data_categories=["identifier or credential-like data"],
            reason="The resource name matches a restricted-data policy rule.",
            requires_approval=True,
            approval_scope="all_modes",
        )
    if _CONFIDENTIAL_HINTS.search(label):
        return ResourceClassification(
            policy_id=f"{POLICY_VERSION}:confidential-name",
            resource=label,
            data_classification="CONFIDENTIAL",
            data_categories=["non-public business record"],
            reason="The resource name matches a confidential business-data rule.",
        )
    return ResourceClassification(
        policy_id=f"{POLICY_VERSION}:internal-default",
        resource=label,
        data_classification="INTERNAL",
        data_categories=["company workspace data"],
        reason="The resource is inside the approved company workspace.",
    )


def classify_action(tool_name: str, args: dict[str, Any]) -> ResourceClassification | None:
    """Return the data policy that applies to a proposed tool invocation."""

    if tool_name == "read_document":
        target = args.get("file_path") or args.get("path") or args.get("filename")
        return classify_resource(target) if target and "{{" not in str(target) else None
    if tool_name == "read_vendor_profile":
        name = args.get("company_name") or args.get("company") or args.get("vendor_name") or "selected vendor"
        return ResourceClassification(
            policy_id=f"{POLICY_VERSION}:vendors",
            resource=f"Vendor profile for {name}",
            data_classification="RESTRICTED",
            data_categories=["tax identifier", "business contact"],
            reason="The onboarding profile contains a tax identifier and contact details.",
            requires_approval=True,
            approval_scope="all_modes",
        )
    if tool_name == "erp_register_vendor":
        return ResourceClassification(
            policy_id=f"{POLICY_VERSION}:vendor-registration",
            resource=f"ERP vendor record for {args.get('name') or args.get('company_name') or 'selected vendor'}",
            data_classification="RESTRICTED",
            data_categories=["tax identifier", "business contact"],
            reason="This action stores restricted onboarding data in the company ledger.",
            requires_approval=True,
            approval_scope="execution",
        )
    if tool_name == "write_file":
        target = args.get("file_path") or args.get("destination") or args.get("path") or "storage/output.txt"
        return ResourceClassification(
            policy_id=f"{POLICY_VERSION}:file-write",
            resource=str(target),
            data_classification="INTERNAL",
            data_categories=["persistent file change"],
            reason="This action creates or replaces a file in persistent sandbox storage.",
            requires_approval=True,
            approval_scope="execution",
        )
    if tool_name == "browser_fill_form":
        return ResourceClassification(
            policy_id=f"{POLICY_VERSION}:form-submit",
            resource=str(args.get("url") or "web form"),
            data_classification="CONFIDENTIAL",
            data_categories=["external data submission"],
            reason="Submitting a form sends data to another application.",
            requires_approval=True,
            approval_scope="execution",
        )
    if tool_name == "api_request":
        method = str(args.get("method", "GET")).upper()
        headers = args.get("headers") or {}
        has_secret = any(re.search(r"authorization|token|api[-_]?key|cookie", str(key), re.I) for key in headers)
        if method in {"POST", "PUT", "PATCH", "DELETE"} or has_secret:
            return ResourceClassification(
                policy_id=f"{POLICY_VERSION}:api-transmission",
                resource=str(args.get("url") or "API endpoint"),
                data_classification="RESTRICTED" if has_secret else "CONFIDENTIAL",
                data_categories=["credential" if has_secret else "external data change"],
                reason="This API call sends protected data or can change an external system.",
                requires_approval=True,
                approval_scope="all_modes" if has_secret else "execution",
            )
    return None


_SECRET_KEY = re.compile(r"(?:password|secret|token|authorization|api[-_]?key|cookie)", re.I)


def redact_action_args(value: Any, key: str = "") -> Any:
    """Create approval-display arguments without leaking secrets or full PII."""

    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_action_args(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_action_args(item, key) for item in value]
    if key.casefold() in {"content", "text", "body"} and isinstance(value, str):
        return f"[content: {len(value)} characters]"
    if "tax" in key.casefold() and isinstance(value, str) and len(value) > 4:
        return value[:3] + "***" + value[-3:]
    if "email" in key.casefold() and isinstance(value, str) and "@" in value:
        local, domain = value.split("@", 1)
        return (local[:1] or "*") + "***@" + domain
    return value
