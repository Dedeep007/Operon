"""API client tools for making REST API calls to external or internal services."""

from typing import Dict, Any, Optional
import requests
from operon.tools.registry import registry

@registry.register(
    name="api_request",
    description="Send a REST HTTP request (GET, POST, PUT, DELETE) to an endpoint with headers and JSON body."
)
def api_request(method: str, url: str, headers: Optional[Dict[str, str]] = None, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute an HTTP API call."""
    clean_method = method.upper().strip()
    try:
        response = requests.request(
            method=clean_method,
            url=url,
            headers=headers or {},
            json=json_body,
            timeout=10
        )
        response.raise_for_status()
        return {
            "status_code": response.status_code,
            "response": response.json() if "application/json" in response.headers.get("content-type", "") else response.text
        }
    except Exception as e:
        raise RuntimeError(f"API request failed: {e}")
