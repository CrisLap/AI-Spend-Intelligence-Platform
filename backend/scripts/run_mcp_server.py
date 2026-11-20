"""Entry point for the MCP server.

Usage:
    # stdio (default): one local client, token from the environment
    MCP_AUTH_TOKEN=<jwt from POST /auth/login> python scripts/run_mcp_server.py

    # streamable HTTP (or --transport sse): every request carries its own
    # `Authorization: Bearer <jwt>` header; MCP_AUTH_TOKEN is not used
    python scripts/run_mcp_server.py --transport streamable-http --port 8765

The HTTP transports bind to 127.0.0.1 by default. Only expose them beyond
localhost behind TLS (a reverse proxy), since the bearer token travels in
every request. See app/mcp/server.py for the tools and the authentication
model.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.mcp.server import check_stdio_token, mcp  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Spend Intelligence MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP transports only")
    parser.add_argument("--port", type=int, default=8765, help="HTTP transports only")
    args = parser.parse_args()

    if args.transport == "stdio":
        check_stdio_token()
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
