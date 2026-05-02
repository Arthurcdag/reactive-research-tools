"""Report storage backends.

The API stores `EvaluationReport` JSON dicts keyed by report id. Two backends:

* :class:`InMemoryStore` - default, ephemeral, loses data on restart.
* :class:`FileStore`     - one ``<report_id>.json`` file under a directory.

Selection at runtime via the ``EBF_REPORT_STORE`` env var:

* unset / ``memory``         - :class:`InMemoryStore`
* ``file:/path/to/dir``      - :class:`FileStore` rooted at the given path

Storage instances are safe for use across requests within one process. The
file backend uses an atomic ``os.replace`` write so concurrent writers do
not produce half-written files; for cross-process locking, fronting it
with a real database is the right move.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator, Protocol


_VALID_ID = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


def _check_id(report_id: str) -> None:
    """Reject ids that could escape the storage directory."""
    if not _VALID_ID.match(report_id):
        raise ValueError(f"invalid report id: {report_id!r}")


class ReportStore(Protocol):
    def put(self, report_id: str, report: dict[str, Any]) -> None: ...
    def get(self, report_id: str) -> dict[str, Any] | None: ...
    def list_ids(self) -> list[str]: ...
    def __contains__(self, report_id: str) -> bool: ...


class InMemoryStore:
    """Process-local dict, lost on restart."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, report_id: str, report: dict[str, Any]) -> None:
        _check_id(report_id)
        with self._lock:
            self._data[report_id] = report

    def get(self, report_id: str) -> dict[str, Any] | None:
        _check_id(report_id)
        with self._lock:
            return self._data.get(report_id)

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._data)

    def __contains__(self, report_id: str) -> bool:
        try:
            _check_id(report_id)
        except ValueError:
            return False
        with self._lock:
            return report_id in self._data


class FileStore:
    """One JSON file per report under ``root``.

    Atomic writes via tempfile + ``os.replace``. No global lock: each report
    id has its own file.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, report_id: str) -> Path:
        _check_id(report_id)
        return self.root / f"{report_id}.json"

    def put(self, report_id: str, report: dict[str, Any]) -> None:
        path = self._path(report_id)
        # write to a sibling tempfile then atomically replace
        fd, tmp = tempfile.mkstemp(prefix=f".{report_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            # tempfile cleanup best-effort
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def get(self, report_id: str) -> dict[str, Any] | None:
        path = self._path(report_id)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def list_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        ids: list[str] = []
        for p in self.root.iterdir():
            if p.suffix != ".json" or p.name.startswith("."):
                continue
            stem = p.stem
            if _VALID_ID.match(stem):
                ids.append(stem)
        return sorted(ids)

    def __contains__(self, report_id: str) -> bool:
        try:
            return self._path(report_id).exists()
        except ValueError:
            return False


def get_store(spec: str | None = None) -> ReportStore:
    """Resolve a store from a spec string.

    ``None`` / ``""`` / ``"memory"`` -> :class:`InMemoryStore`
    ``"file:/some/dir"``             -> :class:`FileStore`

    Falls back to the ``EBF_REPORT_STORE`` env var when ``spec`` is None.
    """
    if spec is None:
        spec = os.environ.get("EBF_REPORT_STORE", "")
    spec = spec.strip()
    if not spec or spec == "memory":
        return InMemoryStore()
    if spec.startswith("file:"):
        path = spec[len("file:"):]
        if not path:
            raise ValueError("file: store spec requires a path: 'file:/path/to/dir'")
        return FileStore(path)
    raise ValueError(f"unknown report store spec: {spec!r}")


def iter_all(store: ReportStore) -> Iterator[dict[str, Any]]:
    for rid in store.list_ids():
        rep = store.get(rid)
        if rep is not None:
            yield rep
