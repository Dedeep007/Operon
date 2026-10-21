"""Tool Registry and Execution Wrapper for Operon."""

from typing import Dict, Any, Callable, Optional, List
from pydantic import BaseModel, Field
import inspect
import traceback

class ToolDefinition(BaseModel):
    """Metadata describing an agent tool."""
    name: str
    description: str
    parameters: Dict[str, Any]
    is_high_risk: bool = False
    requires_approval: bool = False

class ToolExecutionResult(BaseModel):
    """Normalized result returned from tool invocation."""
    success: bool
    tool_name: str
    args: Dict[str, Any]
    data: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None

class ToolRegistry:
    """Central registry and dispatcher for Operon tools."""
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._definitions: Dict[str, ToolDefinition] = {}

    def register(self, name: str, description: str, is_high_risk: bool = False, requires_approval: bool = False):
        """Decorator to register a tool function."""
        def decorator(func: Callable):
            sig = inspect.signature(func)
            params = {}
            for p_name, param in sig.parameters.items():
                params[p_name] = {
                    "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any",
                    "default": None if param.default == inspect.Parameter.empty else param.default,
                    "required": param.default == inspect.Parameter.empty
                }
                
            self._tools[name] = func
            self._definitions[name] = ToolDefinition(
                name=name,
                description=description,
                parameters=params,
                is_high_risk=is_high_risk,
                requires_approval=requires_approval or is_high_risk
            )
            return func
        return decorator

    def get_tool(self, name: str) -> Optional[Callable]:
        return self._tools.get(name)

    def get_definition(self, name: str) -> Optional[ToolDefinition]:
        return self._definitions.get(name)

    def list_definitions(self) -> List[ToolDefinition]:
        return list(self._definitions.values())

    def execute(self, tool_name: str, **kwargs) -> ToolExecutionResult:
        """Safely invoke a tool with normalized error handling."""
        if tool_name not in self._tools:
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                args=kwargs,
                error=f"ToolNotFoundError: Tool '{tool_name}' is not registered.",
                error_type="ToolNotFoundError"
            )

        func = self._tools[tool_name]
        try:
            result = func(**kwargs)
            return ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                args=kwargs,
                data=result
            )
        except Exception as e:
            err_type = type(e).__name__
            err_msg = str(e) or traceback.format_exc()
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                args=kwargs,
                error=f"{err_type}: {err_msg}",
                error_type=err_type
            )

# Global tool registry instance
registry = ToolRegistry()
