import logging

from fastapi import APIRouter, HTTPException

from app.mcp.paypal_client import (
    PayPalMCPClient,
    PayPalMCPConfigurationError,
)

log = logging.getLogger("waypoint.paypal_mcp")

router = APIRouter(
    prefix="/api/mcp/paypal",
    tags=["PayPal MCP"],
)


async def _get_tools():
    try:
        client = PayPalMCPClient()
        return await client.list_tools()

    except PayPalMCPConfigurationError:
        log.error("PayPal MCP credentials are missing.")
        raise HTTPException(
            status_code=503,
            detail="PayPal MCP credentials are not configured.",
        )

    except Exception:
        log.exception("PayPal MCP connection failed")
        raise HTTPException(
            status_code=502,
            detail="PayPal MCP service is temporarily unavailable.",
        )


@router.get("/status")
async def paypal_mcp_status():
    tools = await _get_tools()

    return {
        "connected": True,
        "environment": "sandbox",
        "total_tools": len(tools),
    }


@router.get("/tools")
async def paypal_mcp_tools():
    tools = await _get_tools()

    return {
        "total": len(tools),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in tools
        ],
    }
