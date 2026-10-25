

from collections.abc import Iterable, Sequence
from typing import Any


def copy_rows(cursor: Any, target: str, rows: Iterable[Sequence[Any]]) -> None:

    with cursor.copy(f"COPY {target} FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
