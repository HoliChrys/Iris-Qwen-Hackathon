"""
Semantic auto-filing — routes published reports into TreeFile folders.

Uses a SemanticRouter with local FastEmbed embeddings to match
report content against folder descriptions. When a report is published,
it's automatically placed in the most relevant folder.

Usage:
    from .semantic_filing import auto_file_report

    folder = await auto_file_report(report_content, report_title)
    # Returns: {"folder_id": "f-portfolio", "folder_name": "Portfolio Analysis", "score": 0.82}
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Local FastEmbed provider ────────────────────────────────

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


async def _embed(text: str) -> list[float]:
    """Generate embedding using local FastEmbed."""
    model = _get_model()
    embeddings = list(model.embed([text]))
    return list(embeddings[0])


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Folder definitions (mirrors TreeFile in frontend) ───────

FOLDERS = [
    {
        "id": "f-portfolio",
        "name": "Portfolio Analysis",
        "path": "Loan Reports / Portfolio Analysis",
        "description": "Loan portfolio analysis, disbursement trends, outstanding balances by branch, product type, or customer segment",
        "tags": ["loans", "portfolio", "disbursed", "balance"],
    },
    {
        "id": "f-npl",
        "name": "NPL Monitoring",
        "path": "Loan Reports / NPL Monitoring",
        "description": "Non-performing loan ratios, credit risk monitoring, NPL trends by branch or product, delinquency rates",
        "tags": ["npl", "risk", "credit", "delinquency"],
    },
    {
        "id": "f-channels",
        "name": "By Channel",
        "path": "Transaction Reports / By Channel",
        "description": "Transaction volume and revenue by channel: mobile, ATM, online, branch. Fee revenue, average amounts",
        "tags": ["transactions", "channel", "mobile", "atm", "fee"],
    },
    {
        "id": "root-branches",
        "name": "Branch Performance",
        "path": "Branch Performance",
        "description": "Branch performance comparison, cost-income ratio, profit by region, staff efficiency, operational KPIs",
        "tags": ["branches", "performance", "cost-income", "profit", "efficiency"],
    },
    {
        "id": "root-customers",
        "name": "Customer Analytics",
        "path": "Customer Analytics",
        "description": "Customer segmentation, acquisition channels, churn rate, lifetime value, new customer trends",
        "tags": ["customers", "segmentation", "churn", "acquisition", "ltv"],
    },
    {
        "id": "f-deposits",
        "name": "Deposit Reports",
        "path": "Deposit Reports",
        "description": "Deposit growth, account type analysis, cost of funds, savings vs current vs fixed deposits",
        "tags": ["deposits", "savings", "fixed", "growth", "cost-of-funds"],
    },
]

# Pre-computed folder embeddings (cached on first use)
_folder_embeddings: dict[str, list[float]] = {}


async def _get_folder_embeddings() -> dict[str, list[float]]:
    """Get or compute folder description embeddings."""
    global _folder_embeddings
    if not _folder_embeddings:
        for folder in FOLDERS:
            text = f"{folder['name']}. {folder['description']}"
            _folder_embeddings[folder["id"]] = await _embed(text)
        logger.info("Computed %d folder embeddings", len(_folder_embeddings))
    return _folder_embeddings


# ── Auto-filing function ────────────────────────────────────


async def auto_file_report(
    report_content: dict[str, Any],
    report_title: str = "",
    threshold: float = 0.3,
) -> dict[str, Any] | None:
    """Route a published report to the best matching TreeFile folder.

    Args:
        report_content: The report content dict (title, sections, etc.)
        report_title: Report title
        threshold: Minimum similarity score to file

    Returns:
        Dict with folder_id, folder_name, folder_path, score.
        None if no folder matches above threshold.
    """
    # Build content string from report
    parts = [report_title or report_content.get("title", "")]
    parts.append(report_content.get("executive_summary", ""))
    for section in report_content.get("sections", []):
        parts.append(section.get("title", ""))
    content = " ".join(p for p in parts if p)

    if not content.strip():
        return None

    # Embed report content
    report_embedding = await _embed(content)

    # Compare against all folders
    folder_embeddings = await _get_folder_embeddings()

    best_folder = None
    best_score = -1.0

    for folder in FOLDERS:
        folder_emb = folder_embeddings.get(folder["id"])
        if not folder_emb:
            continue

        score = _cosine_similarity(report_embedding, folder_emb)

        if score > best_score:
            best_score = score
            best_folder = folder

    if best_folder and best_score >= threshold:
        result = {
            "folder_id": best_folder["id"],
            "folder_name": best_folder["name"],
            "folder_path": best_folder["path"],
            "score": round(best_score, 3),
            "tags": best_folder["tags"],
        }
        logger.info(
            "Auto-filed report '%s' → %s (score=%.3f)",
            report_title[:40], best_folder["path"], best_score,
        )
        return result

    logger.info("No folder match for report '%s' (best=%.3f < threshold=%.3f)", report_title[:40], best_score, threshold)
    return None
