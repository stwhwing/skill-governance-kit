"""Entry point for ``python -m skillgov``.

Delegates to :func:`skillgov.cli.main.main` and propagates its integer exit
code (0 success, 1 internal error, 2 CLI error, 3 no data source).
"""

from __future__ import annotations

from skillgov.cli.main import main

if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    raise SystemExit(main())
