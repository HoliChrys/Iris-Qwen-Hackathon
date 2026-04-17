import os
"""
Redpanda Cloud (Kafka-compatible) configuration and client for SB5.

Two access modes:
1. **Dataplane API** (HTTPS, port 443) — topic management via REST.
   Works through proxy environments. Uses service account Bearer token.
2. **Kafka protocol** (TCP, port 9092) — produce/consume via SASL_SSL.
   Requires direct network access. Uses SCRAM-SHA-256 credentials.

Usage::

    from ex.sb5_ai_reporting.kafka_client import (
        get_producer, get_consumer, KAFKA_CONFIG,
        dataplane_list_topics, dataplane_create_topic,
    )

    # Dataplane API (always works)
    topics = dataplane_list_topics()
    dataplane_create_topic("my-topic", partitions=3)

    # Kafka protocol (needs direct TCP)
    producer = get_producer()
    producer.send("sb5.report.requests", value={"query_text": "..."})
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# Redpanda Cloud Configuration
# =============================================================================

KAFKA_CONFIG = {
    "bootstrap_servers": os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092"),
    "security_protocol": "SASL_SSL",
    "sasl_mechanism": "SCRAM-SHA-256",
    "sasl_plain_username": os.environ.get("KAFKA_SASL_USER", ""),
    "sasl_plain_password": os.environ.get("KAFKA_SASL_PASSWORD", ""),
}

# SB5 topic names
TOPICS = {
    "report_requests": "sb5.report.requests",
    "report_events": "sb5.report.events",
    "chart_pipeline": "sb5.chart.pipeline",
}


# =============================================================================
# Redpanda Dataplane API (HTTPS — works through proxies)
# =============================================================================

DATAPLANE_URL = "https://d7d19dugq0q78n6ti9lg.console.ap-southeast-1.mpx.prd.cloud.redpanda.com"
DATAPLANE_CLIENT_ID = os.environ.get("REDPANDA_CLIENT_ID", "")
DATAPLANE_CLIENT_SECRET = os.environ.get("REDPANDA_CLIENT_SECRET", "")
DATAPLANE_AUTH_URL = "https://auth.prd.cloud.redpanda.com/oauth/token"

_token_cache: dict[str, Any] = {}


def _get_dataplane_token() -> str:
    """Get a Bearer token from Redpanda Cloud auth (cached for 24h)."""
    import time

    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > time.time():
        return _token_cache["token"]

    payload = json.dumps({
        "client_id": DATAPLANE_CLIENT_ID,
        "client_secret": DATAPLANE_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }).encode()

    req = urllib.request.Request(DATAPLANE_AUTH_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    ctx = ssl.create_default_context()
    resp = urllib.request.urlopen(req, context=ctx)
    data = json.loads(resp.read().decode())

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600) - 60

    return data["access_token"]


def _dataplane_request(method: str, path: str, body: dict | None = None) -> dict:
    """Make an authenticated request to the Redpanda Dataplane API."""
    token = _get_dataplane_token()
    url = f"{DATAPLANE_URL}{path}"

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    ctx = ssl.create_default_context()
    try:
        resp = urllib.request.urlopen(req, context=ctx)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error = e.read().decode("utf-8", errors="replace")
        logger.error("Dataplane API %s %s: %d %s", method, path, e.code, error[:200])
        raise


def dataplane_list_topics() -> list[dict]:
    """List all topics via Dataplane API."""
    result = _dataplane_request("GET", "/v1alpha2/topics")
    return result.get("topics", [])


def dataplane_create_topic(name: str, partitions: int = 3) -> dict:
    """Create a topic via Dataplane API."""
    return _dataplane_request("POST", "/v1alpha2/topics", {
        "name": name, "partition_count": partitions,
    })


def dataplane_delete_topic(name: str) -> None:
    """Delete a topic via Dataplane API."""
    _dataplane_request("DELETE", f"/v1alpha2/topics/{name}")


def dataplane_get_topic(name: str) -> dict:
    """Get topic details via Dataplane API."""
    return _dataplane_request("GET", f"/v1alpha2/topics/{name}")


# =============================================================================
# Topic management (Dataplane API — preferred)
# =============================================================================


def create_topics() -> list[str]:
    """Create all SB5 topics on Redpanda Cloud via Dataplane API.

    Returns list of topic names created or already existing.
    """
    existing = {t["name"] for t in dataplane_list_topics()}
    created = []

    for label, name in TOPICS.items():
        if name in existing:
            logger.info("Topic already exists: %s", name)
            created.append(name)
            continue
        try:
            dataplane_create_topic(name, partitions=3)
            logger.info("Created topic: %s", name)
            created.append(name)
        except Exception as e:
            logger.error("Error creating topic %s: %s", name, e)

    return created


def create_topics_kafka() -> list[str]:
    """Create topics via Kafka protocol (needs direct TCP access).

    Fallback for environments with direct network access.
    """
    from kafka import KafkaAdminClient
    from kafka.admin import NewTopic
    from kafka.errors import TopicAlreadyExistsError

    admin = KafkaAdminClient(**KAFKA_CONFIG)
    created = []

    for label, name in TOPICS.items():
        try:
            topic = NewTopic(name=name, num_partitions=3, replication_factor=-1)
            admin.create_topics(new_topics=[topic])
            logger.info("Created topic: %s", name)
            created.append(name)
        except TopicAlreadyExistsError:
            logger.info("Topic already exists: %s", name)
            created.append(name)
        except Exception as e:
            logger.error("Error creating topic %s: %s", name, e)

    admin.close()
    return created


def list_topics() -> list[str]:
    """List all topics on the cluster."""
    from kafka import KafkaAdminClient

    admin = KafkaAdminClient(**KAFKA_CONFIG)
    topics = admin.list_topics()
    admin.close()
    return topics


# =============================================================================
# Producer
# =============================================================================


def get_producer(**overrides: Any) -> Any:
    """Create a KafkaProducer pre-configured for Redpanda Cloud.

    Messages are JSON-serialized automatically.

    Args:
        **overrides: Additional KafkaProducer kwargs to override defaults.

    Returns:
        KafkaProducer instance.
    """
    from kafka import KafkaProducer

    config = {
        **KAFKA_CONFIG,
        "value_serializer": lambda v: json.dumps(v, default=str).encode("utf-8"),
        "key_serializer": lambda k: k.encode("utf-8") if isinstance(k, str) else k,
        "acks": "all",
        "retries": 3,
        **overrides,
    }

    return KafkaProducer(**config)


# =============================================================================
# Consumer
# =============================================================================


def get_consumer(
    *topics: str,
    group_id: str = "sb5-ai-reporting",
    **overrides: Any,
) -> Any:
    """Create a KafkaConsumer pre-configured for Redpanda Cloud.

    Messages are JSON-deserialized automatically.

    Args:
        *topics: Topic names to subscribe to.
        group_id: Consumer group ID.
        **overrides: Additional KafkaConsumer kwargs.

    Returns:
        KafkaConsumer instance.
    """
    from kafka import KafkaConsumer

    config = {
        **KAFKA_CONFIG,
        "group_id": group_id,
        "auto_offset_reset": "earliest",
        "enable_auto_commit": True,
        "value_deserializer": lambda v: json.loads(v.decode("utf-8")),
        "consumer_timeout_ms": 10000,
        **overrides,
    }

    consumer = KafkaConsumer(*topics, **config)
    return consumer


# =============================================================================
# Convenience: send a report request
# =============================================================================


def send_report_request(
    query_text: str,
    requester_id: str = "anonymous",
    department: str = "Unknown",
    report_type: str = "general",
    priority: str = "normal",
) -> dict[str, Any]:
    """Send a report request to the sb5.report.requests topic.

    Returns the sent message payload.
    """
    import uuid

    payload = {
        "request_id": str(uuid.uuid4()),
        "requester_id": requester_id,
        "department": department,
        "query_text": query_text,
        "report_type": report_type,
        "priority": priority,
    }

    producer = get_producer()
    future = producer.send(
        TOPICS["report_requests"],
        key=payload["request_id"],
        value=payload,
    )
    result = future.get(timeout=15)
    producer.close()

    logger.info(
        "Sent report request %s to %s (partition=%d, offset=%d)",
        payload["request_id"],
        result.topic,
        result.partition,
        result.offset,
    )

    return payload


def send_report_event(event: dict[str, Any]) -> None:
    """Send a pipeline event to the sb5.report.events topic."""
    producer = get_producer()
    producer.send(
        TOPICS["report_events"],
        key=event.get("request_id", ""),
        value=event,
    )
    producer.flush()
    producer.close()


# =============================================================================
# Connectivity test
# =============================================================================


def test_connection() -> bool:
    """Test if we can connect to Redpanda Cloud.

    Returns True if connection succeeds, False otherwise.
    """
    try:
        from kafka import KafkaAdminClient

        admin = KafkaAdminClient(
            **KAFKA_CONFIG,
            request_timeout_ms=10000,
        )
        topics = admin.list_topics()
        admin.close()
        logger.info("Kafka connection OK, %d topics found", len(topics))
        return True
    except Exception as e:
        logger.warning("Kafka connection failed: %s", e)
        return False
