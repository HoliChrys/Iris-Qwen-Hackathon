"""
SB5 Report Search — Hive pipeline for searching through indexed reports.

Architecture:
    query_channel  -->  [search_handler loop]  -->  answer_channel

The search handler:
1. Receives a natural-language query from query_channel
2. Searches Neo4j (direct Cypher) for matching reports/charts
3. Searches ClickHouse (SQL) for report tracking data
4. Optionally uses Graphiti for semantic search (when service is available)
5. Publishes structured results to answer_channel

Usage with Hive (default mode — streaming):

    search_hive = create_search_hive(app, tracer)
    # Queries arrive via Kafka topic sb5.search.queries
    # Answers published to sb5.search.answers

Usage with hive.ask (request-reply):

    search_hive = create_search_hive(app, tracer)
    result = await search_hive.ask({"query": "loan portfolio reports"})

Usage standalone (no Hive):

    results = await search_reports("loan portfolio by branch")
"""

from __future__ import annotations

import logging
from typing import Any

from tachikoma.hive.core import Hive

logger = logging.getLogger(__name__)


# =============================================================================
# Search backends
# =============================================================================


def _search_neo4j(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search reports and charts in Neo4j via Cypher full-text."""
    from .neo4j_setup import get_client

    neo = get_client()
    if not neo.ping():
        logger.warning("Neo4j unavailable for search")
        return []

    # Search reports by text matching on multiple fields
    terms = query.lower().split()
    where_parts = []
    for term in terms[:5]:  # Max 5 terms
        where_parts.append(
            f"(toLower(r.query_text) CONTAINS '{term}' OR "
            f"toLower(r.report_type) CONTAINS '{term}' OR "
            f"toLower(r.department) CONTAINS '{term}' OR "
            f"toLower(r.entity_id) CONTAINS '{term}')"
        )

    where_clause = " AND ".join(where_parts) if where_parts else "true"

    results = neo.query(f"""
        MATCH (r:ReportRequest)
        WHERE {where_clause}
        OPTIONAL MATCH (r)-[:REQUESTED_BY]->(d:Department)
        OPTIONAL MATCH (r)-[:OF_TYPE]->(t:ReportType)
        OPTIONAL MATCH (r)-[:CONTAINS_CHART]->(c:Chart)
        WITH r, d, t, collect(c) AS charts
        RETURN r.entity_id AS report_id,
               r.state AS state,
               r.query_text AS query_text,
               r.report_type AS report_type,
               d.name AS department,
               t.name AS type_name,
               size(charts) AS chart_count
        LIMIT {max_results}
    """)

    return [{"source": "neo4j", **r} for r in results]


def _search_clickhouse(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search reports in ClickHouse report_tracking table."""
    from .clickhouse_client import ClickHouseCloud
    from .seed_clickhouse import CH_HOST, CH_PASSWORD

    try:
        ch = ClickHouseCloud(host=CH_HOST, password=CH_PASSWORD)
    except Exception:
        logger.warning("ClickHouse unavailable for search")
        return []

    # Build LIKE conditions from query terms
    terms = query.lower().split()
    conditions = []
    for term in terms[:5]:
        conditions.append(
            f"(lower(report_title) LIKE '%{term}%' OR "
            f"lower(department) LIKE '%{term}%' OR "
            f"lower(report_type) LIKE '%{term}%' OR "
            f"lower(query_text) LIKE '%{term}%')"
        )

    where = " AND ".join(conditions) if conditions else "1=1"

    try:
        rows = ch.query(f"""
            SELECT request_id, department, report_type, report_title,
                   status, chart_count, compliance_score, created_at
            FROM dwh.report_tracking
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT {max_results}
        """)
        return [{"source": "clickhouse", **r} for r in rows]
    except Exception as e:
        logger.warning("ClickHouse search failed: %s", e)
        return []


async def _search_graphiti(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Semantic search via Graphiti service (localhost:8002)."""
    import json
    import urllib.request

    try:
        payload = json.dumps({
            "query": query,
            "group_ids": ["iris", "iris-reports", "final"],
            "max_facts": max_results,
        }).encode()

        req = urllib.request.Request(
            "http://localhost:8002/search",
            data=payload,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")

        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())

        results = []
        for fact in data.get("facts", []):
            results.append({
                "source": "graphiti",
                "report_id": fact.get("uuid", ""),
                "report_title": fact.get("fact", ""),
                "report_type": fact.get("name", ""),
                "status": "indexed",
                "created_at": fact.get("created_at", ""),
            })
        return results
    except Exception as e:
        logger.debug("Graphiti search unavailable: %s", e)
        return []


# =============================================================================
# Combined search function
# =============================================================================


async def search_reports(
    query: str,
    max_results: int = 10,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Search across all backends and merge results.

    Args:
        query: Natural-language search query.
        max_results: Max results per source.
        sources: List of sources to search ("neo4j", "clickhouse", "graphiti").
                 Defaults to all available.

    Returns:
        Dict with "query", "results" (merged list), and "sources_queried".
    """
    if sources is None:
        sources = ["neo4j", "clickhouse", "graphiti"]

    all_results = []
    sources_queried = []

    if "neo4j" in sources:
        neo_results = _search_neo4j(query, max_results)
        all_results.extend(neo_results)
        if neo_results:
            sources_queried.append("neo4j")

    if "clickhouse" in sources:
        ch_results = _search_clickhouse(query, max_results)
        all_results.extend(ch_results)
        if ch_results:
            sources_queried.append("clickhouse")

    if "graphiti" in sources:
        g_results = await _search_graphiti(query, max_results)
        all_results.extend(g_results)
        if g_results:
            sources_queried.append("graphiti")

    # Deduplicate by request_id/report_id
    seen = set()
    deduped = []
    for r in all_results:
        rid = r.get("request_id") or r.get("report_id") or r.get("entity_id", "")
        if rid and rid not in seen:
            seen.add(rid)
            deduped.append(r)

    return {
        "query": query,
        "results": deduped[:max_results],
        "total": len(deduped),
        "sources_queried": sources_queried,
    }


# =============================================================================
# Hive search handler (stream loop)
# =============================================================================


async def search_handler(stream: Any) -> None:
    """Hive stream handler for search queries.

    Consumes from the query channel, searches, and yields answers.

    Expected event: {"query": "...", "max_results": 10, "sources": [...]}
    Yields: {"query": "...", "results": [...], "sources_queried": [...]}
    """
    async for event in stream:
        query = event.get("query", "")
        if not query:
            continue

        max_results = event.get("max_results", 10)
        sources = event.get("sources")

        logger.info("Search query: '%s'", query[:80])

        result = await search_reports(query, max_results, sources)

        logger.info(
            "Search results: %d hits from %s",
            result["total"],
            result["sources_queried"],
        )

        yield result


# =============================================================================
# Hive creation
# =============================================================================


def create_search_hive(app: Any, tracer: Any = None) -> Hive:
    """Create a Hive for report search.

    Supports two modes:
    - hive.ask({"query": "..."}) — request-reply (uses switch internally)
    - Streaming via Kafka topic sb5.search.queries

    Args:
        app: Faust/Tachikoma application.
        tracer: Optional ClickHouseTracer.

    Returns:
        Hive instance ready for .ask() or streaming.
    """
    search_hive = Hive(app, name="sb5-search", tracer=tracer)

    async def _search_agent(stream):
        """Stream handler for search queries."""
        async for event in stream:
            query = event.get("query", "")
            if not query:
                yield {"error": "missing 'query' field"}
                continue

            max_results = event.get("max_results", 10)
            result = await search_reports(query, max_results, event.get("sources"))
            yield result

    search_hive.from_input().to_loop(_search_agent)

    logger.info("Search Hive created: sb5-search")
    return search_hive


async def ask_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Standalone search — no Hive needed, just call directly.

    This is the simplest way to search from the frontend API
    or from another pipeline step.
    """
    return await search_reports(query, max_results)
