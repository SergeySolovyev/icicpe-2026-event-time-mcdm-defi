"""Launch the MIRAGE MCP stdio server from any working directory."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


if __name__ == "__main__":
    from mirage.mcp_server import main

    main()
