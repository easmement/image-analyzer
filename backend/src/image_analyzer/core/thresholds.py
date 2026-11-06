"""The verdict thresholds used by classify(), editable at runtime from the settings page.

Stored in <data_dir>/thresholds.json so the server and `make eval` always score with the same
numbers. Defaults are the values chosen from `make eval` on ~/Pictures/sample.
"""

import json
import os
import threading
from dataclasses import asdict, dataclass

from image_analyzer.core.config import settings


@dataclass(frozen=True)
class Thresholds:
    near_phash: int = 12  # near-duplicate: pHash distance at most this ...
    near_dhash: int = 14  # ... and dHash distance at most this
    similar_cosine: float = 0.85  # similar: embedding cosine at least this


DEFAULTS = Thresholds()
_current: Thresholds | None = None
_lock = threading.Lock()


def _path():
    return settings.data_dir / "thresholds.json"


def current() -> Thresholds:
    """The active thresholds (cached; classify() calls this for every pair)."""
    global _current
    if _current is None:
        with _lock:
            if _current is None:
                try:
                    data = json.loads(_path().read_text())
                    _current = Thresholds(**{k: data[k] for k in asdict(DEFAULTS) if k in data})
                except (OSError, ValueError, TypeError):
                    _current = DEFAULTS
    return _current


def save(t: Thresholds) -> None:
    global _current
    with _lock:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(t), indent=2) + "\n")
        os.replace(tmp, _path())  # atomic, so a crash never leaves half a file
        _current = t
