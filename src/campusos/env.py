"""
campusos/env.py – minimal .env loader (stdlib only).

Reads KEY=VALUE lines from a .env file and sets them into os.environ
for any key that is NOT already set.  This preserves shell exports and
lets CI pass variables without a file.

Call ``load_env()`` once at the top of daemon.py and api.py __main__s.
"""

import os
from pathlib import Path


def load_env(path: str | Path | None = None) -> dict[str, str]:
    """Load a .env file into os.environ (missing keys only).

    Parameters
    ----------
    path:
        Path to the .env file.  Defaults to ``.env`` in the current
        working directory, then the directory containing this module,
        then gives up silently if neither exists.

    Returns
    -------
    dict of keys that were actually set (for logging / tests).
    """
    if path is None:
        candidates = [Path(".env"), Path(__file__).parent.parent.parent / ".env"]
        path = next((p for p in candidates if p.is_file()), None)

    if path is None or not Path(path).is_file():
        return {}

    loaded: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
                loaded[key] = val
    return loaded
