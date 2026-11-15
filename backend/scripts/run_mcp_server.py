"""Entry point for the MCP server (stdio transport).

Usage:
    MCP_AUTH_TOKEN=<jwt from POST /auth/login> python scripts/run_mcp_server.py

See app/mcp/server.py for the tool/resource definitions and the
authentication model.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.mcp.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run()
