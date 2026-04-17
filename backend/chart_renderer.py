"""
Chart Renderer — orchestrates the chart WoT pipeline to turn
<blackbox tag="chart"> elements into <chart> elements.

This module:
1. Extracts all blackbox chart elements from a report XML
2. Creates a Chart entity for each
3. Runs each through the chart WoT pipeline (elaborate -> implement -> test -> verify)
4. Replaces the blackbox elements with rendered <chart> elements in the XML tree
"""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

from .chart_agents import ChartElaborator, ChartImplementor, ChartTester, ChartVerifier
from .chart_entities import Chart
from .report_xml import find_blackbox_charts, replace_blackbox_with_chart

logger = logging.getLogger(__name__)

# Agent singletons
_elaborator = ChartElaborator()
_implementor = ChartImplementor()
_tester = ChartTester()
_verifier = ChartVerifier()


async def render_all_charts(
    report_root: ET.Element,
    report_id: str = "",
) -> tuple[ET.Element, list[Chart]]:
    """Process all blackbox chart elements in a report XML tree.

    For each <blackbox tag="chart">:
    1. Create a Chart entity from the blackbox spec
    2. Run it through the chart pipeline (with revision loop)
    3. Build a <chart> XML element with the rendered HTML
    4. Replace the blackbox in the tree

    Args:
        report_root: The report XML root element.
        report_id: Parent report ID.

    Returns:
        Tuple of (updated XML root, list of Chart entities).
    """
    blackboxes = find_blackbox_charts(report_root)
    charts: list[Chart] = []

    if not blackboxes:
        logger.info("No blackbox chart elements found in report")
        return report_root, charts

    logger.info("Found %d blackbox chart elements to render", len(blackboxes))

    for bb_el in blackboxes:
        chart = Chart.from_blackbox(bb_el, report_id=report_id)
        charts.append(chart)

        # Run the chart through the pipeline
        rendered_chart = await _run_chart_pipeline(chart)

        # Build the <chart> XML element
        chart_el = _build_chart_element(rendered_chart)

        # Replace blackbox with chart in the tree
        replaced = replace_blackbox_with_chart(
            report_root,
            rendered_chart.chart_id,
            chart_el,
        )

        if replaced:
            logger.info(
                "Replaced blackbox '%s' with rendered chart (type=%s, %d bytes)",
                rendered_chart.chart_id,
                rendered_chart.chart_type,
                len(rendered_chart.chart_html),
            )
        else:
            logger.warning(
                "Failed to replace blackbox '%s' in XML tree",
                rendered_chart.chart_id,
            )

    return report_root, charts


async def _run_chart_pipeline(chart: Chart) -> Chart:
    """Run a single chart through the WoT pipeline steps.

    Executes: elaborate -> implement -> test -> verify
    With revision loop on verification failure (max 3 iterations).
    """
    max_iterations = 3

    for iteration in range(max_iterations):
        context: dict[str, Any] = {
            "chart_type": chart.chart_type,
            "title": chart.title,
            "description": chart.description,
            "x_axis": chart.x_axis,
            "y_axis": chart.y_axis,
            "data_rows": chart.data_rows or [],
            "stacked": chart.stacked,
            "color_scheme": chart.color_scheme,
            "show_legend": chart.show_legend,
            "show_grid": chart.show_grid,
            "show_values": chart.show_values,
            "style_width": chart.style_width,
            "style_height": chart.style_height,
            "revision_instructions": chart.revision_instructions,
        }

        # Step 1: Elaborate
        logger.info(
            "Chart '%s' - elaborate (iteration %d/%d)",
            chart.chart_id, iteration + 1, max_iterations,
        )
        result = await _elaborator.handle(context)
        context.update(result)

        # Step 2: Implement
        logger.info("Chart '%s' - implement", chart.chart_id)
        result = await _implementor.handle(context)
        context.update(result)
        chart.chart_code = context.get("chart_code", "")
        chart.chart_html = context.get("chart_html", "")

        # Step 3: Test
        logger.info("Chart '%s' - test", chart.chart_id)
        result = await _tester.handle(context)
        context.update(result)
        chart.test_result = context.get("test_result", {})

        # Check test result - if failed, retry implementation
        if not chart.test_result.get("passed", False):
            logger.warning(
                "Chart '%s' test failed: %s — retrying implementation",
                chart.chart_id,
                chart.test_result.get("error", "unknown"),
            )
            chart.chart_code = ""
            chart.chart_html = ""
            continue

        # Step 4: Verify
        logger.info("Chart '%s' - verify", chart.chart_id)
        result = await _verifier.handle(context)
        context.update(result)
        chart.visual_feedback = context.get("visual_feedback", "approved")

        # Check visual feedback
        if chart.visual_feedback == "approved":
            logger.info("Chart '%s' approved!", chart.chart_id)
            break
        else:
            # Need revision
            chart.revision_instructions = context.get("revision_instructions", "")
            chart.revision_count += 1
            logger.info(
                "Chart '%s' needs revision (#%d): %s",
                chart.chart_id,
                chart.revision_count,
                chart.revision_instructions,
            )
            # Clear for next iteration
            chart.chart_code = ""
            chart.chart_html = ""

    # If we exhausted iterations without approval, keep last output
    if not chart.chart_html:
        chart.error_message = "Chart failed after max iterations"
        logger.error("Chart '%s' failed after %d iterations", chart.chart_id, max_iterations)

    return chart


def _build_chart_element(chart: Chart) -> ET.Element:
    """Build a <chart> XML element from a rendered Chart entity.

    Follows the glossary.xml specification for <chart> elements.
    """
    el = ET.Element("chart")
    el.set("id", chart.chart_id)
    el.set("type", chart.chart_type)
    el.set("title", chart.title)
    el.set("status", "ok" if chart.chart_html else "error")

    # chart-html: the rendered SVG/HTML
    html_el = ET.SubElement(el, "chart-html")
    html_el.text = chart.chart_html

    # chart-data: serialized data for auditability
    import json
    data_el = ET.SubElement(el, "chart-data")
    data_el.text = json.dumps({
        "rows": chart.data_rows or [],
        "x_axis": chart.x_axis,
        "y_axis": chart.y_axis,
        "chart_type": chart.chart_type,
    }, default=str)

    return el


async def render_single_chart(chart: Chart) -> Chart:
    """Render a single Chart entity through the pipeline.

    Convenience function for external callers who already have a Chart entity.
    """
    return await _run_chart_pipeline(chart)
