"""Entry point for the packaged executable.

PyInstaller runs its entry script as ``__main__``, where relative imports do
not resolve; this thin wrapper imports the package the normal way.
"""

import sys

from lagscope.cli import main

if __name__ == "__main__":
    sys.exit(main())
