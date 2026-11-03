"""Extractor REST genérico: autenticación, paginación, reintentos e incremental."""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from ..config import get_settings
from ..registry.models import (
    BearerAuth,
    CursorPagination,
    HeaderAuth,
    OffsetPagination,
    PagePagination,
    QueryAuth,
    RestConnection,
    SourceSpec,
)

log = logging.getLogger(__name__)
RETRY_STATUS = {429, 500, 502, 503, 504}


class ExtractionError(Exception):
    pass


def dig(obj: Any, path: str | None) -> Any:
    """Sigue una ruta con puntos dentro de un JSON ('data.items')."""
    if not path:
        return obj
    for part in path.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def retry_wait(value: str | None, default: float) -> float:
    """Segundos de espera según 'Retry-After', que puede ser un número o una fecha HTTP."""
    if not value:
        return default
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return default


class RestExtractor:
    def __init__(self, spec: SourceSpec, cursor_value: str | None, client: httpx.Client | None = None):
        if not isinstance(spec.connection, RestConnection):
            raise TypeError("RestExtractor requiere una conexión REST")
        self.spec = spec
        self.conn: RestConnection = spec.connection
        self.cursor_value = cursor_value
        self._client = client

    # ------------------------------------------------------------------ armado
    def base_params(self) -> dict[str, Any]:
        params = dict(self.conn.params)
        inc = self.spec.incremental
        if inc and inc.filter and self.cursor_value is not None:
            expr = inc.filter.template.format(field=inc.cursor_field, value=self.cursor_value)
            prev = params.get(inc.filter.param)
            params[inc.filter.param] = f"({prev}) AND ({expr})" if prev else expr
        if isinstance(self.conn.auth, QueryAuth) and self.conn.auth.value:
            params[self.conn.auth.param] = self.conn.auth.value
        return params

    def headers(self) -> dict[str, str]:
        h = {"User-Agent": get_settings().http_user_agent, "Accept": "application/json", **self.conn.headers}
        auth = self.conn.auth
        if isinstance(auth, HeaderAuth) and auth.value:
            h[auth.header] = auth.value
        elif isinstance(auth, BearerAuth) and auth.token:
            h["Authorization"] = f"Bearer {auth.token}"
        return h

    # --------------------------------------------------------------- peticiones
    def _request(self, client: httpx.Client, params: dict[str, Any]) -> Any:
        last_exc: Exception | None = None
        headers = self.headers()   # por petición: también aplica si el cliente viene de fuera
        for attempt in range(self.conn.max_retries + 1):
            try:
                if self.conn.method == "GET":
                    r = client.get(self.conn.base_url, params=params, headers=headers)
                else:
                    r = client.post(self.conn.base_url, json=params, headers=headers)
                if r.status_code in RETRY_STATUS and attempt < self.conn.max_retries:
                    wait = retry_wait(r.headers.get("Retry-After"), 2**attempt)
                    log.warning("HTTP %s, reintento %s en %.1fs", r.status_code, attempt + 1, wait)
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last_exc = e
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code not in RETRY_STATUS:
                    raise ExtractionError(f"HTTP {e.response.status_code}: {e.response.text[:300]}") from e
                if attempt < self.conn.max_retries:
                    time.sleep(2**attempt)
        raise ExtractionError(f"se agotaron los reintentos: {last_exc}")

    def _records(self, payload: Any) -> list[dict[str, Any]]:
        data = dig(payload, self.conn.records_path)
        if data is None:
            return []
        if not isinstance(data, list):
            raise ExtractionError(f"'records_path' no apunta a una lista (tipo: {type(data).__name__})")
        return [r if isinstance(r, dict) else {"value": r} for r in data]

    # ---------------------------------------------------------------- iteración
    def pages(self) -> Iterator[list[dict[str, Any]]]:
        """Entrega páginas de registros hasta agotar la fuente o llegar a max_records."""
        cap = self.spec.max_records
        seen = 0
        pag = self.spec.pagination
        base = self.base_params()
        client = self._client or httpx.Client(timeout=self.conn.timeout_s)
        try:
            if isinstance(pag, OffsetPagination):
                offset = 0
                while True:
                    size = pag.page_size if cap is None else min(pag.page_size, cap - seen)
                    if size <= 0:
                        break
                    recs = self._records(self._request(client, {**base, pag.limit_param: size, pag.offset_param: offset}))
                    if recs:
                        seen += len(recs)
                        yield recs
                    if len(recs) < size:
                        break
                    offset += len(recs)
            elif isinstance(pag, PagePagination):
                page = pag.first_page
                while cap is None or seen < cap:
                    recs = self._records(self._request(client, {**base, pag.page_param: page, pag.size_param: pag.page_size}))
                    if cap is not None:
                        recs = recs[: cap - seen]
                    if recs:
                        seen += len(recs)
                        yield recs
                    if len(recs) < pag.page_size:
                        break
                    page += 1
            elif isinstance(pag, CursorPagination):
                cursor: Any = None
                while cap is None or seen < cap:
                    params = {**base, **({pag.cursor_param: cursor} if cursor else {})}
                    payload = self._request(client, params)
                    recs = self._records(payload)
                    if cap is not None:
                        recs = recs[: cap - seen]
                    if recs:
                        seen += len(recs)
                        yield recs
                    cursor = dig(payload, pag.next_cursor_path)
                    if not cursor or not recs:
                        break
            else:
                recs = self._records(self._request(client, base))
                yield recs[:cap] if cap else recs
        finally:
            if self._client is None:
                client.close()
