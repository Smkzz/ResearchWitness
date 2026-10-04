"""Load the small synthetic verifier examples shipped with the package."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def capability_examples() -> dict[str, dict[str, Any]]:
    path = Path(__file__).with_name('capability_examples.json')
    return json.loads(path.read_text(encoding='utf-8'))
