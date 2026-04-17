"""
XML Report Builder — generates report documents conforming to glossary.xml.

The report is first built as an XML tree with <blackbox tag="chart"> placeholders.
The chart WoT pipeline later replaces each blackbox with a rendered <chart> element.
Finally, the XML is converted to HTML for display.

Flow:
    1. ReportGenerator agent produces a GeneratedReport (dataclass)
    2. ReportXMLBuilder converts it into an XML tree with blackbox chart tags
    3. Chart WoT pipeline processes each blackbox -> <chart> with HTML
    4. xml_to_html() renders the final report as HTML
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# XML Builder: GeneratedReport dict -> XML tree with blackbox chart tags
# ---------------------------------------------------------------------------


class ReportXMLBuilder:
    """Builds an XML report document from report data.

    Automatically creates <blackbox tag="chart"> elements for sections
    that contain chart data, following the glossary.xml specification.
    """

    def __init__(self, report_id: str | None = None):
        self.report_id = report_id or str(uuid.uuid4())

    def build(
        self,
        report: dict[str, Any],
        data_result: dict[str, Any],
        parsed_query: dict[str, Any],
    ) -> ET.Element:
        """Build the full XML report tree.

        Args:
            report: GeneratedReport.to_dict() output.
            data_result: DataResult.to_dict() output.
            parsed_query: ParsedQuery.to_dict() output.

        Returns:
            Root <report> Element with blackbox chart placeholders.
        """
        root = ET.Element("report")
        root.set("id", self.report_id)
        root.set("type", report.get("report_type", "general"))
        root.set("lang", "fr")
        root.set("generated-at", report.get("generated_at", datetime.now().isoformat()))

        # -- Meta block -------------------------------------------------------
        meta = ET.SubElement(root, "meta")

        title_el = ET.SubElement(meta, "title")
        title_el.text = report.get("title", "Untitled Report")

        for ds in report.get("data_sources", []):
            ds_el = ET.SubElement(meta, "data-source")
            ds_el.set("domain", ds)
            table = f"dwh.fact_{ds}"
            ds_el.set("table", table)
            ds_el.set("period", parsed_query.get("time_range", "last_month"))

        if report.get("methodology_note"):
            meth = ET.SubElement(meta, "methodology")
            meth.text = report["methodology_note"]

        # -- Executive summary -------------------------------------------------
        summary = ET.SubElement(root, "summary")
        summary.text = report.get("executive_summary", "")

        # -- Sections ----------------------------------------------------------
        chart_counter = 0
        for i, section_data in enumerate(report.get("sections", [])):
            section = ET.SubElement(root, "section")
            section.set("id", f"section-{i + 1}")
            section.set("title", section_data.get("title", f"Section {i + 1}"))

            # Add paragraph content
            para = ET.SubElement(section, "paragraph")
            para.text = section_data.get("content", "")

            # Add key metrics from data_summary
            data_summary = section_data.get("data_summary", {})
            for label, value in data_summary.items():
                km = ET.SubElement(section, "key-metric")
                km.set("label", label)
                km.set("value", str(value))
                if isinstance(value, float) and value < 1:
                    km.set("unit", "%")

            # Create blackbox chart placeholder if section has chart_type
            chart_type = section_data.get("chart_type")
            if chart_type and chart_type != "table":
                chart_counter += 1
                blackbox = self._build_blackbox_chart(
                    chart_id=f"chart-{chart_counter}",
                    chart_type=chart_type,
                    title=section_data.get("title", "Chart"),
                    section_data=section_data,
                    data_result=data_result,
                    parsed_query=parsed_query,
                )
                section.append(blackbox)

            # Create a table for tabular data
            if chart_type == "table" or (not chart_type and data_result.get("rows")):
                table_el = self._build_data_table(data_result, parsed_query)
                if table_el is not None:
                    section.append(table_el)

        # If no sections produced charts but we have data, add a default chart
        if chart_counter == 0 and data_result.get("rows"):
            section = ET.SubElement(root, "section")
            section.set("id", "section-auto-chart")
            section.set("title", "Data Visualization")

            para = ET.SubElement(section, "paragraph")
            para.text = "Automatic visualization of report data."

            blackbox = self._build_blackbox_chart(
                chart_id="chart-auto",
                chart_type=self._infer_chart_type(parsed_query),
                title=f"{parsed_query.get('domain', 'Data')} Overview",
                section_data={},
                data_result=data_result,
                parsed_query=parsed_query,
            )
            section.append(blackbox)

        # -- Footer ------------------------------------------------------------
        footer = ET.SubElement(root, "footer")
        compliance_el = ET.SubElement(footer, "compliance")
        compliance_el.set("passed", "false")
        compliance_el.set("score", "0.0")

        review_el = ET.SubElement(footer, "review")
        review_el.set("status", "pending")

        return root

    def _build_blackbox_chart(
        self,
        chart_id: str,
        chart_type: str,
        title: str,
        section_data: dict[str, Any],
        data_result: dict[str, Any],
        parsed_query: dict[str, Any],
    ) -> ET.Element:
        """Build a <blackbox tag="chart"> element per glossary spec."""
        bb = ET.Element("blackbox")
        bb.set("tag", "chart")
        bb.set("id", chart_id)
        bb.set("title", title)
        bb.set("description", f"Chart visualization for: {title}")

        # -- chart-spec --------------------------------------------------------
        spec = ET.SubElement(bb, "chart-spec")
        spec.set("type", chart_type)

        dimensions = parsed_query.get("dimensions", [])
        metrics = parsed_query.get("metrics", [])

        if dimensions:
            spec.set("x-axis", dimensions[0])
        if metrics:
            spec.set("y-axis", ",".join(metrics))
        if len(dimensions) > 1:
            spec.set("group-by", dimensions[1])
        if chart_type == "bar" and len(metrics) > 1:
            spec.set("stacked", "true")
        spec.set("color-scheme", "corporate-blue")

        # -- data-ref with inline rows ----------------------------------------
        rows = data_result.get("rows", [])
        if rows:
            data_ref = ET.SubElement(bb, "data-ref")
            data_ref.set("source", "inline")
            columns = data_result.get("columns", [])
            data_ref.set("columns", ",".join(columns))

            for row in rows:
                row_el = ET.SubElement(bb, "row")
                for k, v in row.items():
                    row_el.set(k, str(v))

        # -- style-hint --------------------------------------------------------
        style = ET.SubElement(bb, "style-hint")
        style.set("width", "100%")
        style.set("height", "400px")
        style.set("show-legend", "true")
        style.set("show-grid", "true")
        style.set("show-values", "false")
        style.set("font-size", "12px")

        return bb

    def _build_data_table(
        self,
        data_result: dict[str, Any],
        parsed_query: dict[str, Any],
    ) -> ET.Element | None:
        """Build a <table> element from data rows."""
        rows = data_result.get("rows", [])
        if not rows:
            return None

        columns = data_result.get("columns", list(rows[0].keys()))

        table = ET.Element("table")
        table.set("caption", f"Data: {parsed_query.get('domain', 'unknown')}")

        thead = ET.SubElement(table, "thead")
        tr = ET.SubElement(thead, "tr")
        for col in columns:
            th = ET.SubElement(tr, "th")
            th.text = col

        tbody = ET.SubElement(table, "tbody")
        for row in rows[:20]:  # Limit to 20 rows
            tr = ET.SubElement(tbody, "tr")
            for col in columns:
                td = ET.SubElement(tr, "td")
                val = row.get(col, "")
                td.text = str(round(val, 2)) if isinstance(val, float) else str(val)

        return table

    def _infer_chart_type(self, parsed_query: dict[str, Any]) -> str:
        """Infer the best chart type from the query structure."""
        metrics = parsed_query.get("metrics", [])
        dimensions = parsed_query.get("dimensions", [])

        if len(dimensions) == 0:
            return "bar"
        if len(metrics) == 1 and len(dimensions) == 1:
            return "bar"
        if any(d in ("period", "month", "date") for d in dimensions):
            return "line"
        if len(metrics) > 2:
            return "bar"
        return "bar"


# ---------------------------------------------------------------------------
# XML utilities
# ---------------------------------------------------------------------------


def report_to_xml_string(root: ET.Element) -> str:
    """Serialize a report XML tree to a formatted string."""
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def parse_report_xml(xml_string: str) -> ET.Element:
    """Parse a report XML string into an Element tree."""
    return ET.fromstring(xml_string)


def find_blackbox_charts(root: ET.Element) -> list[ET.Element]:
    """Find all <blackbox tag="chart"> elements in a report."""
    return [el for el in root.iter("blackbox") if el.get("tag") == "chart"]


def replace_blackbox_with_chart(
    root: ET.Element,
    blackbox_id: str,
    chart_element: ET.Element,
) -> bool:
    """Replace a blackbox element with a rendered chart element.

    Finds the blackbox by ID in the tree and replaces it in-place
    within its parent.

    Returns:
        True if replacement succeeded, False if blackbox not found.
    """
    for parent in root.iter():
        for i, child in enumerate(parent):
            if child.tag == "blackbox" and child.get("id") == blackbox_id:
                parent.remove(child)
                parent.insert(i, chart_element)
                return True
    return False


# ---------------------------------------------------------------------------
# XML -> HTML renderer
# ---------------------------------------------------------------------------


def xml_to_html(root: ET.Element) -> str:
    """Convert a final report XML tree (with rendered charts) to HTML.

    Walks the XML tree and generates styled HTML output.
    """
    parts: list[str] = []

    report_title = ""
    meta_el = root.find("meta")
    if meta_el is not None:
        title_el = meta_el.find("title")
        if title_el is not None and title_el.text:
            report_title = title_el.text

    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="fr">')
    parts.append("<head>")
    parts.append(f"  <title>{_esc(report_title)}</title>")
    parts.append('  <meta charset="UTF-8">')
    parts.append("  <style>")
    parts.append(_report_css())
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<div class="report">')

    # Title
    parts.append(f'<h1 class="report-title">{_esc(report_title)}</h1>')

    # Meta
    if meta_el is not None:
        parts.append('<div class="meta">')
        for ds in meta_el.findall("data-source"):
            parts.append(
                f'<span class="data-source">Source: {_esc(ds.get("domain", ""))} '
                f'({_esc(ds.get("table", ""))}), period: {_esc(ds.get("period", ""))}</span>'
            )
        meth = meta_el.find("methodology")
        if meth is not None and meth.text:
            parts.append(f'<p class="methodology"><em>{_esc(meth.text)}</em></p>')
        parts.append("</div>")

    # Summary
    summary = root.find("summary")
    if summary is not None and summary.text:
        parts.append(f'<div class="summary"><p>{_esc(summary.text)}</p></div>')

    # Sections
    for section in root.findall("section"):
        sec_title = section.get("title", "")
        parts.append(f'<section id="{_esc(section.get("id", ""))}">')
        parts.append(f"<h2>{_esc(sec_title)}</h2>")

        for child in section:
            if child.tag == "paragraph" and child.text:
                parts.append(f"<p>{_esc(child.text)}</p>")

            elif child.tag == "key-metric":
                label = child.get("label", "")
                value = child.get("value", "")
                unit = child.get("unit", "")
                trend = child.get("trend", "")
                trend_cls = f" trend-{trend}" if trend else ""
                parts.append(
                    f'<div class="key-metric{trend_cls}">'
                    f'<span class="metric-label">{_esc(label)}</span>'
                    f'<span class="metric-value">{_esc(value)}{_esc(unit)}</span>'
                    f"</div>"
                )

            elif child.tag == "table":
                parts.append(_table_to_html(child))

            elif child.tag == "chart":
                parts.append(_chart_to_html(child))

            elif child.tag == "blackbox":
                # Unreplaced blackbox — render as placeholder
                parts.append(_blackbox_placeholder_html(child))

        parts.append("</section>")

    # Footer
    footer = root.find("footer")
    if footer is not None:
        parts.append('<footer class="report-footer">')
        comp = footer.find("compliance")
        if comp is not None:
            passed = comp.get("passed", "false")
            score = comp.get("score", "0")
            cls = "compliance-pass" if passed == "true" else "compliance-fail"
            parts.append(
                f'<div class="{cls}">Compliance: {"PASS" if passed == "true" else "FAIL"} '
                f"(score: {score})</div>"
            )
        rev = footer.find("review")
        if rev is not None:
            parts.append(
                f'<div class="review-status">Review: {_esc(rev.get("status", "pending"))}</div>'
            )
        parts.append("</footer>")

    parts.append("</div>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Escape HTML entities."""
    import html
    return html.escape(text)


def _table_to_html(table_el: ET.Element) -> str:
    """Convert a <table> XML element to HTML."""
    lines = ['<table class="data-table">']
    caption = table_el.get("caption")
    if caption:
        lines.append(f"<caption>{_esc(caption)}</caption>")

    thead = table_el.find("thead")
    if thead is not None:
        lines.append("<thead>")
        for tr in thead.findall("tr"):
            lines.append("<tr>")
            for th in tr.findall("th"):
                lines.append(f"<th>{_esc(th.text or '')}</th>")
            lines.append("</tr>")
        lines.append("</thead>")

    tbody = table_el.find("tbody")
    if tbody is not None:
        lines.append("<tbody>")
        for tr in tbody.findall("tr"):
            lines.append("<tr>")
            for td in tr.findall("td"):
                lines.append(f"<td>{_esc(td.text or '')}</td>")
            lines.append("</tr>")
        lines.append("</tbody>")

    lines.append("</table>")
    return "\n".join(lines)


def _chart_to_html(chart_el: ET.Element) -> str:
    """Convert a rendered <chart> element to HTML."""
    chart_html_el = chart_el.find("chart-html")
    if chart_html_el is not None and chart_html_el.text:
        return (
            f'<div class="chart-container" id="{_esc(chart_el.get("id", ""))}">'
            f'<h3 class="chart-title">{_esc(chart_el.get("title", ""))}</h3>'
            f'{chart_html_el.text}'
            f'</div>'
        )
    return f'<div class="chart-error">Chart {_esc(chart_el.get("id", ""))} failed to render.</div>'


def _blackbox_placeholder_html(bb: ET.Element) -> str:
    """Render an unreplaced blackbox as a visual placeholder."""
    return (
        f'<div class="blackbox-placeholder">'
        f'<span class="bb-icon">&#9744;</span> '
        f'<strong>{_esc(bb.get("title", "Pending"))}</strong> '
        f'<em>(chart rendering pending)</em>'
        f'</div>'
    )


def _report_css() -> str:
    """Return embedded CSS for the report HTML."""
    return """
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 20px; background: #f5f6fa; }
    .report { max-width: 1000px; margin: 0 auto; background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
    .report-title { color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 12px; }
    .meta { color: #666; font-size: 0.9rem; margin-bottom: 20px; }
    .data-source { display: block; margin: 4px 0; }
    .methodology { font-style: italic; color: #888; }
    .summary { background: #e8eaf6; padding: 16px 20px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #1a237e; }
    section { margin: 30px 0; }
    h2 { color: #283593; border-bottom: 1px solid #c5cae9; padding-bottom: 8px; }
    .key-metric { display: inline-block; background: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px 20px; margin: 6px 8px 6px 0; }
    .metric-label { display: block; font-size: 0.8rem; color: #888; text-transform: uppercase; }
    .metric-value { display: block; font-size: 1.5rem; font-weight: 700; color: #1a237e; }
    .trend-up .metric-value::after { content: ' \\2191'; color: #2e7d32; }
    .trend-down .metric-value::after { content: ' \\2193'; color: #c62828; }
    .data-table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.9rem; }
    .data-table th { background: #1a237e; color: #fff; padding: 10px 12px; text-align: left; }
    .data-table td { padding: 8px 12px; border-bottom: 1px solid #e0e0e0; }
    .data-table tbody tr:hover { background: #f5f5f5; }
    .chart-container { margin: 20px 0; padding: 16px; border: 1px solid #e0e0e0; border-radius: 6px; background: #fafafa; }
    .chart-title { margin: 0 0 12px 0; color: #283593; font-size: 1rem; }
    .chart-error { color: #c62828; padding: 12px; background: #ffebee; border-radius: 4px; }
    .blackbox-placeholder { padding: 20px; background: #fff3e0; border: 2px dashed #ff9800; border-radius: 6px; text-align: center; color: #e65100; margin: 16px 0; }
    .bb-icon { font-size: 1.5rem; }
    .report-footer { margin-top: 40px; padding-top: 20px; border-top: 2px solid #e0e0e0; font-size: 0.85rem; color: #666; }
    .compliance-pass { color: #2e7d32; font-weight: 600; }
    .compliance-fail { color: #c62828; font-weight: 600; }
    .review-status { margin-top: 4px; }
    """
