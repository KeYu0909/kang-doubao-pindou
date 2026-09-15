#!/usr/bin/env python3
"""Standard-library supervisor; never installs missing dependencies."""
from pindou.cli import main
if __name__ == '__main__':
    raise SystemExit(main())
