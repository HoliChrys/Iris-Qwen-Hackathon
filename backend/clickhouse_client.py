"""
ClickHouse Cloud client for the SB5 AI Reporting project.

Uses the ClickHouse HTTP interface via stdlib urllib.request, which
correctly handles proxy environments where urllib3 (used by
clickhouse-connect) fails.

Provides a simple query/command interface sufficient for:
- Creating schemas (DDL)
- Inserting data
- Querying data with result parsing
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
class ClickHouseCloud:
    """Lightweight ClickHouse HTTP client that works through proxies.

    Uses the ClickHouse HTTP interface (port 8443 for HTTPS) with
    Basic authentication.  All queries go through stdlib urllib.request
    which properly negotiates proxy tunnels.

    Usage::

        ch = ClickHouseCloud(
            host="xxx.germanywestcentral.azure.clickhouse.cloud",
            password="your_password",
        )
        # Simple query
        result = ch.query("SELECT count() FROM system.tables")
        print(result)  # [{'count()': 42}]

        # DDL
        ch.command("CREATE TABLE IF NOT EXISTS ...")

        # Insert
        ch.insert("my_table", columns=["id", "name"], rows=[[1, "foo"]])
    """

    host: str = ""
    port: int = 8443
    user: str = "default"
    password: str = ""
    database: str = "default"
    secure: bool = True
    _ssl_ctx: ssl.SSLContext = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._ssl_ctx is None:
            self._ssl_ctx = ssl.create_default_context()

    @property
    def base_url(self) -> str:
        proto = "https" if self.secure else "http"
        return f"{proto}://{self.host}:{self.port}/"

    def _auth_header(self) -> str:
        creds = f"{self.user}:{self.password}".encode()
        return f"Basic {base64.b64encode(creds).decode()}"

    def _request(
        self,
        query: str,
        *,
        params: dict[str, str] | None = None,
        content_type: str = "text/plain",
    ) -> str:
        """Execute a raw HTTP request to ClickHouse."""
        url = self.base_url
        if params:
            qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
            url = f"{url}?{qs}"

        req = urllib.request.Request(
            url,
            data=query.encode("utf-8"),
            method="POST",
        )
        req.add_header("Authorization", self._auth_header())
        req.add_header("Content-Type", content_type)

        try:
            resp = urllib.request.urlopen(req, context=self._ssl_ctx)
            body = resp.read().decode("utf-8")
            return body
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(
                "ClickHouse HTTP error %d: %s\nQuery: %s",
                e.code,
                error_body[:500],
                query[:200],
            )
            raise RuntimeError(
                f"ClickHouse error {e.code}: {error_body[:300]}"
            ) from e

    def command(self, query: str) -> str:
        """Execute a DDL or non-returning query (CREATE, INSERT, ALTER, etc.)."""
        result = self._request(query)
        logger.debug("Command OK: %s", query[:100])
        return result.strip()

    def query(self, query: str) -> list[dict[str, Any]]:
        """Execute a SELECT query and return rows as list of dicts.

        Automatically appends FORMAT JSONEachRow if no FORMAT is specified.
        """
        q = query.strip().rstrip(";")
        if "FORMAT" not in q.upper():
            q += " FORMAT JSONEachRow"

        raw = self._request(q)
        if not raw.strip():
            return []

        rows = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def query_scalar(self, query: str) -> Any:
        """Execute a query and return a single scalar value."""
        q = query.strip().rstrip(";")
        raw = self._request(q).strip()
        # Try to parse as number
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            return raw

    def insert(
        self,
        table: str,
        columns: list[str],
        rows: list[list[Any]],
        database: str | None = None,
    ) -> int:
        """Insert rows into a table using JSONEachRow format.

        Args:
            table: Table name.
            columns: Column names.
            rows: List of row values (same order as columns).
            database: Override database.

        Returns:
            Number of rows inserted.
        """
        db = database or self.database
        full_table = f"{db}.{table}" if db != "default" else table

        json_rows = []
        for row in rows:
            obj = dict(zip(columns, row, strict=False))
            json_rows.append(json.dumps(obj, default=str))

        payload = "\n".join(json_rows)
        query = f"INSERT INTO {full_table} FORMAT JSONEachRow"
        self._request(query + "\n" + payload)

        logger.info("Inserted %d rows into %s", len(rows), full_table)
        return len(rows)

    def table_exists(self, table: str, database: str | None = None) -> bool:
        """Check if a table exists."""
        db = database or self.database
        result = self.query_scalar(
            f"SELECT count() FROM system.tables "
            f"WHERE database = '{db}' AND name = '{table}'"
        )
        return int(result) > 0

    def ping(self) -> bool:
        """Test connectivity."""
        try:
            result = self.query_scalar("SELECT 1")
            return result == 1
        except Exception:
            return False
