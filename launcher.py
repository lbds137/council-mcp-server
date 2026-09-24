#!/usr/bin/env python3
"""Entry point for the installed Council MCP server.

scripts/install.sh installs the council package into the venv beside this file,
and Claude runs this file with that venv's python. It stays a file here, not a
console script, because the server finds credentials/ and .env next to the
script it was started from (sys.argv[0]).
"""

from council.main import main

if __name__ == "__main__":
    main()
