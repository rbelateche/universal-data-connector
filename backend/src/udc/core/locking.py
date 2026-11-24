"""Serialise access to a store's DuckDB connection.

A ``duckdb.DuckDBPyConnection`` must not be used by two threads at once, and
FastAPI runs sync endpoints in a thread pool. Concurrent requests sharing a
store's connection returned wrong results and could crash the process
(segfault). Stores hold an ``RLock`` and mark every method that touches the
connection with ``@serialized``. This also makes ``MAX(id) + 1`` id
allocation safe.
"""

import functools
import threading
from collections.abc import Callable
from typing import Concatenate, ParamSpec, Protocol, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class HasLock(Protocol):
    _lock: threading.RLock


S = TypeVar("S", bound=HasLock)


def serialized(method: Callable[Concatenate[S, P], R]) -> Callable[Concatenate[S, P], R]:
    """Run *method* while holding ``self._lock``."""

    def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> R:
        with self._lock:
            return method(self, *args, **kwargs)

    functools.update_wrapper(wrapper, method)
    return wrapper
