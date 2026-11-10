from collections.abc import Awaitable, Callable
from functools import wraps

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .client import compare_school_records, get_school, search_schools

READ_ONLY = ToolAnnotations(
    read_only_hint=True, idempotent_hint=True, destructive_hint=False, open_world_hint=True
)


def _tool_errors[**P, R](function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(function)
    async def invoke(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await function(*args, **kwargs)
        except (ValueError, OSError, httpx.HTTPError) as exc:
            raise ToolError(str(exc)) from None

    return invoke


def create_server() -> MCPServer:
    mcp = MCPServer("jp-school-code-mcp")
    mcp.tool(annotations=READ_ONLY)(_tool_errors(search_schools))
    mcp.tool(annotations=READ_ONLY)(_tool_errors(get_school))
    mcp.tool(annotations=READ_ONLY)(_tool_errors(compare_school_records))
    return mcp
