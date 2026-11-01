import os
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

PAYPAL_MCP_URL = "https://mcp.sandbox.paypal.com/sse"


class PayPalMCPConfigurationError(Exception):
    """Raised only when PayPal MCP credentials are missing."""


class PayPalMCPClient:
    """Async client for PayPal Sandbox MCP."""

    def __init__(self) -> None:
        self.access_token = os.getenv("PAYPAL_SANDBOX_ACCESS_TOKEN")

        if not self.access_token:
            raise PayPalMCPConfigurationError(
                "PAYPAL_SANDBOX_ACCESS_TOKEN environment variable is missing."
            )

    async def _execute(
        self,
        operation: str,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        async with sse_client(
            url=PAYPAL_MCP_URL,
            headers=headers,
            timeout=30,
            sse_read_timeout=300,
        ) as (read_stream, write_stream):

            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                if operation == "list_tools":
                    result = await session.list_tools()
                    return result.tools

                if operation == "call_tool" and tool_name:
                    return await session.call_tool(
                        tool_name,
                        arguments=arguments or {},
                    )

                raise ValueError("Unsupported MCP operation.")

    async def list_tools(self) -> list[Any]:
        return await self._execute("list_tools")

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        return await self._execute(
            "call_tool",
            tool_name=tool_name,
            arguments=arguments,
        )
