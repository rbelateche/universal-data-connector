"""JSON REST API connector with pluggable pagination."""

from collections.abc import Iterator
from typing import Any

import httpx

from udc.connectors.base import BaseConnector


class JsonApiConnector(BaseConnector):
    """
    Fetch data from a paginated JSON REST API.

    Supports two pagination modes:

    * **next_key** — the response body contains a field (e.g. ``"next"``)
      whose value is the URL of the next page.  Set ``next_key="next"``.
    * **No pagination** — fetches a single URL and returns the array.

    The *data_key* parameter names the field in the response body that
    holds the array of records (e.g. ``"results"`` for DRF, ``"data"`` for
    many APIs).  If the response *is* the array, leave it as ``None``.

    A custom *transport* can be injected for testing (httpx.MockTransport).
    """

    def __init__(
        self,
        url: str,
        data_key: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        next_key: str | None = None,
        max_pages: int = 100,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._data_key = data_key
        self._headers = headers or {}
        self._params = params or {}
        self._next_key = next_key
        self._max_pages = max_pages
        self._transport = transport
        self._client: httpx.Client | None = None
        self._cache: list[dict[str, Any]] | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._client = httpx.Client(
            headers=self._headers,
            timeout=30.0,
            follow_redirects=True,
            transport=self._transport,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self._cache = None

    # ── helpers ───────────────────────────────────────────────────────────

    def _assert_connected(self) -> httpx.Client:
        if self._client is None:
            raise RuntimeError("Call connect() before reading data.")
        return self._client

    def _extract_rows(self, body: Any) -> list[dict[str, Any]]:
        if isinstance(body, list):
            return [r for r in body if isinstance(r, dict)]
        if isinstance(body, dict):
            if self._data_key:
                data = body.get(self._data_key, [])
                return [r for r in data if isinstance(r, dict)]
            return [body]
        return []

    def _fetch_all(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache

        client = self._assert_connected()
        rows: list[dict[str, Any]] = []
        url: str | None = self._url
        params = dict(self._params)
        pages = 0

        while url and pages < self._max_pages:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
            rows.extend(self._extract_rows(body))
            pages += 1

            if self._next_key and isinstance(body, dict):
                next_val = body.get(self._next_key)
                url = next_val if isinstance(next_val, str) else None
                params = {}
            else:
                break

        self._cache = rows
        return rows

    # ── data access ───────────────────────────────────────────────────────

    def sample(self, n: int = 100) -> list[dict[str, Any]]:
        return self._fetch_all()[:n]

    def stream(
        self,
        batch_size: int = 1000,
        watermark_col: str | None = None,
        watermark_val: Any = None,
    ) -> Iterator[list[dict[str, Any]]]:
        rows = self._fetch_all()

        if watermark_col is not None and watermark_val is not None:
            rows = [r for r in rows if r.get(watermark_col) is not None and r[watermark_col] > watermark_val]

        for i in range(0, len(rows), batch_size):
            yield rows[i : i + batch_size]

    def get_schema(self) -> dict[str, str]:
        rows = self._fetch_all()
        if not rows:
            return {}
        return {k: type(v).__name__ for k, v in rows[0].items()}
