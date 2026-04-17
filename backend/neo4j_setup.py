import os
"""
Neo4j Aura setup for the SB5 AI Reporting project.

Uses the Neo4j Query API v2 (HTTPS port 443) via neo4j_client.py,
which works through proxy environments.

Provides:
1. Connection configuration for Neo4j Aura
2. Schema creation (constraints, indexes)
3. Entity graph operations (index reports, charts, transitions)
4. Graph queries (by department, with charts, stats)

StatefulRecords (ReportRequest, Chart) are indexed in Neo4j as nodes
with relationships:

    (:ReportRequest)-[:REQUESTED_BY]->(:Department)
    (:ReportRequest)-[:OF_TYPE]->(:ReportType)
    (:ReportRequest)-[:CONTAINS_CHART]->(:Chart)
    (:Entity)-[:TRANSITIONED]->(:Transition)

Run::

    python -m ex.sb5_ai_reporting.neo4j_setup           # create schema
    python -m ex.sb5_ai_reporting.neo4j_setup --verify   # verify connection + stats
"""

from __future__ import annotations

import logging
from typing import Any

from .neo4j_client import Neo4jCloud

logger = logging.getLogger(__name__)

# =============================================================================
# Neo4j Aura Configuration
# =============================================================================

NEO4J_HOST = os.environ.get("NEO4J_HOST", "localhost")
NEO4J_PORT = 443
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = "neo4j"
NEO4J_SECURE = True

# For EntityCluster / bolt protocol
NEO4J_URI = f"neo4j+s://{NEO4J_HOST}"
NEO4J_AUTH = (NEO4J_USER, NEO4J_PASSWORD)


def get_client() -> Neo4jCloud:
    """Get a Neo4j HTTP client."""
    return Neo4jCloud(
        host=NEO4J_HOST,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
    )


# =============================================================================
# Schema (constraints + indexes)
# =============================================================================

SCHEMA_QUERIES = [
    # ReportRequest
    "CREATE CONSTRAINT report_request_id IF NOT EXISTS "
    "FOR (r:ReportRequest) REQUIRE r.entity_id IS UNIQUE",

    "CREATE INDEX report_request_state IF NOT EXISTS "
    "FOR (r:ReportRequest) ON (r.state)",

    "CREATE INDEX report_request_type IF NOT EXISTS "
    "FOR (r:ReportRequest) ON (r.report_type)",

    "CREATE INDEX report_request_dept IF NOT EXISTS "
    "FOR (r:ReportRequest) ON (r.department)",

    # Chart
    "CREATE CONSTRAINT chart_id IF NOT EXISTS "
    "FOR (c:Chart) REQUIRE c.entity_id IS UNIQUE",

    "CREATE INDEX chart_state IF NOT EXISTS "
    "FOR (c:Chart) ON (c.state)",

    "CREATE INDEX chart_type IF NOT EXISTS "
    "FOR (c:Chart) ON (c.chart_type)",

    # Generic Entity
    "CREATE CONSTRAINT entity_id IF NOT EXISTS "
    "FOR (e:Entity) REQUIRE e.id IS UNIQUE",

    "CREATE INDEX entity_type IF NOT EXISTS "
    "FOR (e:Entity) ON (e.entity_type)",

    "CREATE INDEX entity_state IF NOT EXISTS "
    "FOR (e:Entity) ON (e.state)",
]


def create_schema() -> list[str]:
    """Create constraints and indexes. Returns list of executed statements."""
    neo = get_client()
    executed = []

    for stmt in SCHEMA_QUERIES:
        try:
            neo.execute(stmt)
            label = stmt.split("IF NOT EXISTS")[0].strip()
            executed.append(label)
            logger.info("Schema OK: %s", label)
        except Exception as e:
            logger.warning("Schema: %s — %s", stmt[:60], e)

    return executed


# =============================================================================
# Entity indexing
# =============================================================================


def index_report_request(data: dict[str, Any]) -> None:
    """Index a ReportRequest as a Neo4j node with relationships."""
    neo = get_client()
    neo.execute(
        """
        MERGE (r:ReportRequest:Entity {entity_id: $entity_id})
        SET r.request_id = $request_id,
            r.requester_id = $requester_id,
            r.department = $department,
            r.query_text = $query_text,
            r.report_type = $report_type,
            r.priority = $priority,
            r.state = $state,
            r.updated_at = toString(datetime())
        WITH r
        MERGE (d:Department {name: $department})
        MERGE (r)-[:REQUESTED_BY]->(d)
        WITH r
        MERGE (t:ReportType {name: $report_type})
        MERGE (r)-[:OF_TYPE]->(t)
        """,
        entity_id=data.get("request_id", data.get("id", "")),
        request_id=data.get("request_id", ""),
        requester_id=data.get("requester_id", ""),
        department=data.get("department", ""),
        query_text=data.get("query_text", "")[:500],
        report_type=data.get("report_type", ""),
        priority=data.get("priority", "normal"),
        state=data.get("state", "draft"),
    )


def index_chart(data: dict[str, Any], report_id: str = "") -> None:
    """Index a Chart as a Neo4j node, linked to its parent report."""
    neo = get_client()

    # Create/update chart node
    neo.execute(
        """
        MERGE (c:Chart:Entity {entity_id: $entity_id})
        SET c.chart_id = $chart_id,
            c.chart_type = $chart_type,
            c.title = $title,
            c.state = $state,
            c.revision_count = $revision_count,
            c.updated_at = toString(datetime())
        """,
        entity_id=data.get("chart_id", ""),
        chart_id=data.get("chart_id", ""),
        chart_type=data.get("chart_type", "bar"),
        title=data.get("title", ""),
        state=data.get("state", "elaboration"),
        revision_count=data.get("revision_count", 0),
    )

    # Link to report if provided
    if report_id:
        neo.execute(
            """
            MATCH (r:ReportRequest:Entity {entity_id: $report_id})
            MATCH (c:Chart:Entity {entity_id: $chart_id})
            MERGE (r)-[:CONTAINS_CHART]->(c)
            """,
            report_id=report_id,
            chart_id=data.get("chart_id", ""),
        )


def index_transition(
    entity_id: str,
    from_state: str,
    to_state: str,
    trigger: str = "",
) -> None:
    """Record a state transition in the graph."""
    neo = get_client()
    neo.execute(
        """
        MATCH (e {entity_id: $entity_id})
        SET e.state = $to_state
        WITH e
        CREATE (t:Transition {
            entity_id: $entity_id,
            from_state: $from_state,
            to_state: $to_state,
            trigger: $trigger,
            timestamp: toString(datetime())
        })
        CREATE (e)-[:TRANSITIONED]->(t)
        """,
        entity_id=entity_id,
        from_state=from_state,
        to_state=to_state,
        trigger=trigger,
    )


# =============================================================================
# Graph queries
# =============================================================================


def query_reports_by_department(department: str) -> list[dict]:
    neo = get_client()
    return neo.query(
        "MATCH (r:ReportRequest)-[:REQUESTED_BY]->(d:Department {name: $dept}) "
        "RETURN r.entity_id AS id, r.report_type AS type, r.state AS state",
        dept=department,
    )


def query_report_with_charts(report_id: str) -> list[dict]:
    neo = get_client()
    return neo.query(
        "MATCH (r:ReportRequest {entity_id: $id})-[:CONTAINS_CHART]->(c:Chart) "
        "RETURN c.chart_id AS chart_id, c.chart_type AS type, "
        "c.title AS title, c.state AS state",
        id=report_id,
    )


def get_graph_stats() -> dict[str, Any]:
    neo = get_client()
    stats = {}

    for label in ["ReportRequest", "Chart", "Department", "ReportType", "Transition"]:
        count = neo.query_scalar(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        stats[label] = count or 0

    rels = neo.query(
        "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt"
    )
    stats["relationships"] = {r["rel_type"]: r["cnt"] for r in rels}

    return stats


# =============================================================================
# CLI
# =============================================================================


if __name__ == "__main__":
    import sys

    if "--verify" in sys.argv:
        neo = get_client()
        print(f"Ping: {neo.ping()}")
        if neo.ping():
            stats = get_graph_stats()
            print(f"Graph stats: {stats}")
    else:
        neo = get_client()
        if not neo.ping():
            print("Cannot connect to Neo4j Aura. Is the instance ready?")
            sys.exit(1)
        print(f"Connected to Neo4j at {NEO4J_HOST}")
        executed = create_schema()
        print(f"Schema: {len(executed)} statements executed")
        for s in executed:
            print(f"  {s}")
