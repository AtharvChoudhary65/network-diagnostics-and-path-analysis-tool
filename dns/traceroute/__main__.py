"""Allows running the package directly: python -m traceroute <target>"""

import sys

from .traceroute import _main

sys.exit(_main())
