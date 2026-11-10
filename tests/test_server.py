import sys

import pytest
from mcp import Client, StdioServerParameters

from jp_school_code_mcp import create_server


@pytest.mark.asyncio
async def test_stdio_tool_contract() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "jp_school_code_mcp"])
    async with Client(params, mode="legacy", read_timeout_seconds=10) as client:
        result = await client.list_tools()
    assert {tool.name for tool in result.tools} == {
        "compare_school_records",
        "search_schools",
        "get_school",
    }
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in result.tools)
    assert len(await create_server().list_tools()) == 3
