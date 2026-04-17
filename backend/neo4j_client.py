"""
Neo4j HTTP client for the IRIS AI Reporting project.

Supports two modes:
1. **Local Neo4j** (Community/Enterprise) — Transaction API at /db/{db}/tx/commit
2. **Neo4j Aura** (Cloud) — Query API v2 at /db/{db}/query/v2

Autodetects which API to use based on the host (local = port 7474 HTTP,
Aura = port 443 HTTPS with *.databases.neo4j.io).

Usage::

    neo = Neo4jCloud(host="172.19.0.2", port=7474, password="password", secure=False)
    result = neo.query("RETURN 1 AS n")
    print(result)  # [{"n": 1}]
"""
from __future__ import annotations

import base64
import json
import logging
import ssl
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Neo4jCloud:
    """Neo4j HTTP client — works with both local and Aura instances."""

    host: str = ""
    port: int = 7474
    user: str = "neo4j"
    password: str = ""
    database: str = "neo4j"
    secure: bool = False
    _ssl_ctx: ssl.SSLContext = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._ssl_ctx is None:
            self._ssl_ctx = ssl.create_default_context()
        # Auto-detect Aura (HTTPS on port 443)
        if ".databases.neo4j.io" in self.host:
            self.secure = True
            self.port = 443

    @property
    def _is_aura(self) -> bool:
        return ".databases.neo4j.io" in self.host

    @property
    def base_url(self) -> str:
        proto = "https" if self.secure else "http"
        return f"{proto}://{self.host}:{self.port}"

    @property
    def query_url(self) -> str:
        if self._is_aura:
            return f"{self.base_url}/db/{self.database}/query/v2"
        return f"{self.base_url}/db/{self.database}/tx/commit"

    def _auth_header(self) -> str:
        creds = f"{self.user}:{self.password}".encode()
        return f"Basic {base64.b64encode(creds).decode()}"

    def _request(self, statement: str, parameters: dict[str, Any] | None = None) -> dict:
        """Execute a Cypher statement via the appropriate API."""
        if self._is_aura:
            return self._request_aura(statement, parameters)
        return self._request_local(statement, parameters)

    def _request_local(self, statement: str, parameters: dict[str, Any] | None = None) -> dict:
        """Execute via Transaction API (/tx/commit)."""
        stmt: dict[str, Any] = {"statement": statement}
        if parameters:
            stmt["parameters"] = parameters

        payload = {"statements": [stmt]}
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(self.query_url, data=data, method="POST")
        req.add_header("Authorization", self._auth_header())
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            ctx = self._ssl_ctx if self.secure else None
            resp = urllib.request.urlopen(req, context=ctx)
            body = resp.read().decode("utf-8")
            result = json.loads(body)

            if result.get("errors"):
                err = result["errors"][0]
                raise RuntimeError(f"Neo4j error {err.get('code', 'unknown')}: {err.get('message', '')}")

            # Transform tx response to match our query() format
            results = result.get("results", [])
            if not results:
                return {"data": {"fields": [], "values": []}}

            first = results[0]
            columns = first.get("columns", [])
            rows_data = first.get("data", [])

            return {
                "data": {
                    "fields": columns,
                    "values": [row.get("row", []) for row in rows_data],
                }
            }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error("Neo4j HTTP error %d: %s", e.code, error_body[:500])
            raise RuntimeError(f"Neo4j error {e.code}: {error_body[:300]}") from e

    def _request_aura(self, statement: str, parameters: dict[str, Any] | None = None) -> dict:
        """Execute via Query API v2 (/query/v2) for Aura."""
        payload: dict[str, Any] = {"statement": statement}
        if parameters:
            payload["parameters"] = parameters

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.query_url, data=data, method="POST")
        req.add_header("Authorization", self._auth_header())
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            resp = urllib.request.urlopen(req, context=self._ssl_ctx)
            body = resp.read().decode("utf-8")
            return json.loads(body)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error("Neo4j HTTP error %d: %s", e.code, error_body[:500])
            raise RuntimeError(f"Neo4j error {e.code}: {error_body[:300]}") from e

    def query(self, statement: str, **parameters: Any) -> list[dict[str, Any]]:
        """Execute a read query and return rows as list of dicts."""
        result = self._request(statement, parameters or None)
        data = result.get("data", {})
        fields = data.get("fields", [])
        values = data.get("values", [])

        rows = []
        for row_values in values:
            row = {}
            for i, field_name in enumerate(fields):
                val = row_values[i] if i < len(row_values) else None
                row[field_name] = val
            rows.append(row)

        return rows

    def execute(self, statement: str, **parameters: Any) -> dict:
        """Execute a write statement (CREATE, MERGE, DELETE, etc.)."""
        result = self._request(statement, parameters or None)
        return result

    def query_scalar(self, statement: str, **parameters: Any) -> Any:
        """Execute a query and return a single scalar value."""
        rows = self.query(statement, **parameters)
        if rows:
            first_key = next(iter(rows[0]))
            return rows[0][first_key]
        return None

    def ping(self) -> bool:
        """Test connectivity."""
        try:
            result = self.query_scalar("RETURN 1 AS n")
            return result == 1
        except Exception:
            return False
