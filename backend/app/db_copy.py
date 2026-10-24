"""Bulk inserts through PostgreSQL COPY.

COPY is several times faster than INSERT ... executemany for the tens of
thousands of rows a snapshot load or recompute writes.
"""

from collections.abc import Iterable, Sequence
from typing import Any


def copy_rows(cursor: Any, target: str, rows: Iterable[Sequence[Any]]) -> None:
    """COPY rows into ``target``, e.g. ``'app.service_scores (service_id, score)'``."""
    with cursor.copy(f"COPY {target} FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
