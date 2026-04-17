"""
Chart generation agents for the chart WoT pipeline.

Agents:
    ChartElaborator    -- Analyzes blackbox spec and plans the chart implementation
    ChartImplementor   -- Generates actual HTML/SVG chart code
    ChartTester        -- Validates the generated chart code
    ChartVerifier      -- Visually verifies the rendered chart output
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Any

from .llm import chat_completion

logger = logging.getLogger(__name__)


# =============================================================================
# Color palettes
# =============================================================================

COLOR_PALETTES = {
    "corporate-blue": ["#1a237e", "#283593", "#3949ab", "#5c6bc0", "#7986cb", "#9fa8da"],
    "warm": ["#e65100", "#f57c00", "#ff9800", "#ffb74d", "#ffe0b2", "#fff3e0"],
    "cool": ["#006064", "#00838f", "#0097a7", "#00bcd4", "#4dd0e1", "#80deea"],
    "mixed": ["#1a237e", "#2e7d32", "#c62828", "#f57c00", "#6a1b9a", "#00838f"],
    "pastel": ["#90caf9", "#a5d6a7", "#ef9a9a", "#ffcc80", "#ce93d8", "#80cbc4"],
}


def _get_colors(scheme: str, count: int) -> list[str]:
    """Get a list of colors from a palette, cycling if needed."""
    palette = COLOR_PALETTES.get(scheme, COLOR_PALETTES["corporate-blue"])
    return [palette[i % len(palette)] for i in range(count)]


# =============================================================================
# ChartElaborator
# =============================================================================

ELABORATOR_SYSTEM_PROMPT = """\
You are a data visualization expert. Given a chart specification and data,
you must plan the best way to visualize this data.

Analyze:
1. What story the data tells
2. Whether the requested chart type is appropriate
3. What axis labels, scales, and formatting to use
4. Any data transformations needed (sorting, aggregation)

Use the plan_chart tool to return your analysis.
"""

ELABORATOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "plan_chart",
            "description": "Return the chart implementation plan",
            "parameters": {
                "type": "object",
                "properties": {
                    "recommended_type": {
                        "type": "string",
                        "enum": ["bar", "line", "pie", "dot", "area", "heatmap"],
                    },
                    "sort_by": {"type": "string", "description": "Column to sort data by"},
                    "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                    "x_label": {"type": "string"},
                    "y_label": {"type": "string"},
                    "notes": {"type": "string", "description": "Implementation notes"},
                },
                "required": ["recommended_type", "x_label", "y_label"],
            },
        },
    },
]


@dataclass
class ChartElaborator:
    """Analyzes the chart spec and plans implementation."""

    name: str = "chart_elaborator"

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Event: {chart_type, title, x_axis, y_axis, data_rows, revision_instructions?}
        Returns: {elaboration: {recommended_type, sort_by, ...}}
        """
        chart_type = event.get("chart_type", "bar")
        title = event.get("title", "")
        x_axis = event.get("x_axis", "")
        y_axis = event.get("y_axis", "")
        data_rows = event.get("data_rows", [])
        revision = event.get("revision_instructions", "")

        user_msg = (
            f"Chart request: type={chart_type}, title='{title}'\n"
            f"X-axis: {x_axis}, Y-axis: {y_axis}\n"
            f"Data sample ({len(data_rows)} rows): {json.dumps(data_rows[:5], default=str)}"
        )
        if revision:
            user_msg += f"\n\nREVISION INSTRUCTIONS: {revision}"

        messages = [
            {"role": "system", "content": ELABORATOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        try:
            result = await chat_completion(messages, tools=ELABORATOR_TOOLS)
            for tc in result.get("tool_calls", []):
                if tc["function"]["name"] == "plan_chart":
                    args = json.loads(tc["function"]["arguments"])
                    return {"elaboration": args}
        except Exception as e:
            logger.warning("LLM elaboration failed: %s", e)

        # Fallback
        return {
            "elaboration": {
                "recommended_type": chart_type,
                "sort_by": x_axis,
                "sort_order": "asc",
                "x_label": x_axis.replace("_", " ").title(),
                "y_label": y_axis.split(",")[0].replace("_", " ").title() if y_axis else "Value",
                "notes": "Fallback elaboration — using defaults.",
            }
        }


# =============================================================================
# ChartImplementor
# =============================================================================


def _format_number(val: float) -> str:
    """Format a number for display on charts."""
    if abs(val) >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"{val / 1_000:.1f}K"
    if isinstance(val, float) and val < 1:
        return f"{val:.2%}"
    return f"{val:,.0f}"


def _generate_bar_chart_svg(
    data_rows: list[dict],
    x_field: str,
    y_fields: list[str],
    colors: list[str],
    title: str,
    x_label: str,
    y_label: str,
    width: int,
    height: int,
    show_legend: bool,
    show_grid: bool,
    show_values: bool,
    stacked: bool,
) -> str:
    """Generate an inline SVG bar chart."""
    if not data_rows or not y_fields:
        return '<div class="chart-empty">No data to display</div>'

    margin = {"top": 40, "right": 20, "bottom": 60, "left": 80}
    if show_legend:
        margin["right"] = 140
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    # Extract values
    labels = [str(row.get(x_field, f"Item {i}")) for i, row in enumerate(data_rows)]
    all_values = []
    for field in y_fields:
        vals = [float(row.get(field, 0)) for row in data_rows]
        all_values.append(vals)

    # Compute max value
    if stacked:
        max_val = max(sum(vs[i] for vs in all_values) for i in range(len(data_rows)))
    else:
        max_val = max(v for vs in all_values for v in vs)
    max_val = max_val * 1.1 if max_val > 0 else 1

    n_bars = len(data_rows)
    n_series = len(y_fields)
    bar_group_w = plot_w / max(n_bars, 1)
    bar_w = (bar_group_w * 0.7) / (1 if stacked else n_series)
    bar_gap = bar_group_w * 0.15

    lines = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:{width}px;height:{height}px;font-family:sans-serif">']

    # Grid lines
    if show_grid:
        n_grid = 5
        for i in range(n_grid + 1):
            y = margin["top"] + plot_h - (plot_h * i / n_grid)
            val = max_val * i / n_grid
            lines.append(f'<line x1="{margin["left"]}" y1="{y}" x2="{margin["left"] + plot_w}" '
                         f'y2="{y}" stroke="#e0e0e0" stroke-width="1"/>')
            lines.append(f'<text x="{margin["left"] - 8}" y="{y + 4}" text-anchor="end" '
                         f'font-size="11" fill="#666">{_format_number(val)}</text>')

    # Bars
    for si, (field, vals) in enumerate(zip(y_fields, all_values, strict=False)):
        color = colors[si % len(colors)]
        for bi, val in enumerate(vals):
            if stacked:
                # Stack offset
                offset = sum(all_values[s][bi] for s in range(si))
                x = margin["left"] + bi * bar_group_w + bar_gap
                bar_h = (val / max_val) * plot_h
                offset_h = (offset / max_val) * plot_h
                y = margin["top"] + plot_h - offset_h - bar_h
                w = bar_group_w * 0.7
            else:
                x = margin["left"] + bi * bar_group_w + bar_gap + si * bar_w
                bar_h = (val / max_val) * plot_h
                y = margin["top"] + plot_h - bar_h
                w = bar_w

            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bar_h:.1f}" '
                         f'fill="{color}" rx="2"/>')

            if show_values:
                lines.append(f'<text x="{x + w / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" '
                             f'font-size="10" fill="#333">{_format_number(val)}</text>')

    # X-axis labels
    for bi, label in enumerate(labels):
        x = margin["left"] + bi * bar_group_w + bar_group_w / 2
        y = margin["top"] + plot_h + 20
        display_label = label[:12] + ".." if len(label) > 14 else label
        lines.append(f'<text x="{x:.1f}" y="{y}" text-anchor="middle" '
                     f'font-size="11" fill="#333">{display_label}</text>')

    # Axis labels
    lines.append(f'<text x="{margin["left"] + plot_w / 2}" y="{height - 8}" '
                 f'text-anchor="middle" font-size="12" fill="#666">{x_label}</text>')
    lines.append(f'<text x="14" y="{margin["top"] + plot_h / 2}" '
                 f'text-anchor="middle" font-size="12" fill="#666" '
                 f'transform="rotate(-90, 14, {margin["top"] + plot_h / 2})">{y_label}</text>')

    # Title
    lines.append(f'<text x="{width / 2}" y="20" text-anchor="middle" '
                 f'font-size="14" font-weight="bold" fill="#1a237e">{title}</text>')

    # Legend
    if show_legend and n_series > 1:
        lx = margin["left"] + plot_w + 10
        for si, field in enumerate(y_fields):
            ly = margin["top"] + si * 20
            lines.append(f'<rect x="{lx}" y="{ly}" width="12" height="12" fill="{colors[si % len(colors)]}" rx="2"/>')
            display_field = field.replace("_", " ")[:16]
            lines.append(f'<text x="{lx + 16}" y="{ly + 10}" font-size="11" fill="#333">{display_field}</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def _generate_line_chart_svg(
    data_rows: list[dict],
    x_field: str,
    y_fields: list[str],
    colors: list[str],
    title: str,
    x_label: str,
    y_label: str,
    width: int,
    height: int,
    show_legend: bool,
    show_grid: bool,
    show_values: bool,
) -> str:
    """Generate an inline SVG line chart."""
    if not data_rows or not y_fields:
        return '<div class="chart-empty">No data to display</div>'

    margin = {"top": 40, "right": 20, "bottom": 60, "left": 80}
    if show_legend:
        margin["right"] = 140
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    labels = [str(row.get(x_field, f"P{i}")) for i, row in enumerate(data_rows)]
    all_values = [[float(row.get(f, 0)) for row in data_rows] for f in y_fields]

    max_val = max(v for vs in all_values for v in vs) * 1.1
    max_val = max_val if max_val > 0 else 1
    n = len(data_rows)

    lines = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:{width}px;height:{height}px;font-family:sans-serif">']

    # Grid
    if show_grid:
        for i in range(6):
            y = margin["top"] + plot_h - (plot_h * i / 5)
            val = max_val * i / 5
            lines.append(f'<line x1="{margin["left"]}" y1="{y}" x2="{margin["left"] + plot_w}" '
                         f'y2="{y}" stroke="#e0e0e0"/>')
            lines.append(f'<text x="{margin["left"] - 8}" y="{y + 4}" text-anchor="end" '
                         f'font-size="11" fill="#666">{_format_number(val)}</text>')

    # Lines + dots
    for si, (field, vals) in enumerate(zip(y_fields, all_values, strict=False)):
        color = colors[si % len(colors)]
        points = []
        for i, val in enumerate(vals):
            px = margin["left"] + (i / max(n - 1, 1)) * plot_w
            py = margin["top"] + plot_h - (val / max_val) * plot_h
            points.append((px, py, val))

        polyline = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in points)
        lines.append(f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2.5"/>')

        for px, py, val in points:
            lines.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{color}"/>')
            if show_values:
                lines.append(f'<text x="{px:.1f}" y="{py - 8:.1f}" text-anchor="middle" '
                             f'font-size="10" fill="#333">{_format_number(val)}</text>')

    # X labels
    for i, label in enumerate(labels):
        x = margin["left"] + (i / max(n - 1, 1)) * plot_w
        display = label[:12] + ".." if len(label) > 14 else label
        lines.append(f'<text x="{x:.1f}" y="{margin["top"] + plot_h + 20}" '
                     f'text-anchor="middle" font-size="11" fill="#333">{display}</text>')

    # Axis labels & title
    lines.append(f'<text x="{margin["left"] + plot_w / 2}" y="{height - 8}" '
                 f'text-anchor="middle" font-size="12" fill="#666">{x_label}</text>')
    lines.append(f'<text x="14" y="{margin["top"] + plot_h / 2}" text-anchor="middle" '
                 f'font-size="12" fill="#666" '
                 f'transform="rotate(-90, 14, {margin["top"] + plot_h / 2})">{y_label}</text>')
    lines.append(f'<text x="{width / 2}" y="20" text-anchor="middle" '
                 f'font-size="14" font-weight="bold" fill="#1a237e">{title}</text>')

    # Legend
    if show_legend and len(y_fields) > 1:
        lx = margin["left"] + plot_w + 10
        for si, field in enumerate(y_fields):
            ly = margin["top"] + si * 20
            lines.append(f'<rect x="{lx}" y="{ly}" width="12" height="12" fill="{colors[si % len(colors)]}" rx="2"/>')
            lines.append(f'<text x="{lx + 16}" y="{ly + 10}" font-size="11" fill="#333">{field.replace("_", " ")[:16]}</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def _generate_pie_chart_svg(
    data_rows: list[dict],
    label_field: str,
    value_field: str,
    colors: list[str],
    title: str,
    width: int,
    height: int,
    show_legend: bool,
) -> str:
    """Generate an inline SVG pie chart."""
    if not data_rows or not value_field:
        return '<div class="chart-empty">No data to display</div>'

    labels = [str(row.get(label_field, f"Slice {i}")) for i, row in enumerate(data_rows)]
    values = [float(row.get(value_field, 0)) for row in data_rows]
    total = sum(values) or 1

    cx, cy = width / 2 - (60 if show_legend else 0), height / 2
    r = min(cx - 40, cy - 40)

    lines_out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
                 f'style="width:{width}px;height:{height}px;font-family:sans-serif">']

    # Title
    lines_out.append(f'<text x="{width / 2}" y="20" text-anchor="middle" '
                     f'font-size="14" font-weight="bold" fill="#1a237e">{title}</text>')

    angle = -90  # Start at top
    for i, (label, val) in enumerate(zip(labels, values, strict=False)):
        pct = val / total
        sweep = pct * 360
        color = colors[i % len(colors)]

        start_rad = math.radians(angle)
        end_rad = math.radians(angle + sweep)

        x1 = cx + r * math.cos(start_rad)
        y1 = cy + r * math.sin(start_rad)
        x2 = cx + r * math.cos(end_rad)
        y2 = cy + r * math.sin(end_rad)

        large_arc = 1 if sweep > 180 else 0

        d = f"M {cx},{cy} L {x1:.1f},{y1:.1f} A {r},{r} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z"
        lines_out.append(f'<path d="{d}" fill="{color}" stroke="#fff" stroke-width="2"/>')

        # Percentage label
        mid_rad = math.radians(angle + sweep / 2)
        lx = cx + r * 0.65 * math.cos(mid_rad)
        ly = cy + r * 0.65 * math.sin(mid_rad)
        if pct > 0.05:
            lines_out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                             f'font-size="11" fill="#fff" font-weight="bold">{pct:.0%}</text>')

        angle += sweep

    # Legend
    if show_legend:
        lx = cx + r + 30
        for i, (label, val) in enumerate(zip(labels, values, strict=False)):
            ly = 50 + i * 22
            lines_out.append(f'<rect x="{lx}" y="{ly}" width="12" height="12" '
                             f'fill="{colors[i % len(colors)]}" rx="2"/>')
            display = label[:18]
            lines_out.append(f'<text x="{lx + 16}" y="{ly + 10}" font-size="11" fill="#333">{display}</text>')

    lines_out.append("</svg>")
    return "\n".join(lines_out)


@dataclass
class ChartImplementor:
    """Generates HTML/SVG chart code from the elaboration plan and data."""

    name: str = "chart_implementor"

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Event: {chart_type, title, x_axis, y_axis, data_rows, elaboration, ...style params}
        Returns: {chart_code: str, chart_html: str}
        """
        elaboration = event.get("elaboration", {})
        chart_type = elaboration.get("recommended_type", event.get("chart_type", "bar"))
        title = event.get("title", "Chart")
        x_axis = event.get("x_axis", "")
        y_axis_str = event.get("y_axis", "")
        y_fields = [f.strip() for f in y_axis_str.split(",") if f.strip()] if y_axis_str else []
        data_rows = event.get("data_rows", [])
        stacked = event.get("stacked", False)
        color_scheme = event.get("color_scheme", "corporate-blue")
        show_legend = event.get("show_legend", True)
        show_grid = event.get("show_grid", True)
        show_values = event.get("show_values", False)

        x_label = elaboration.get("x_label", x_axis.replace("_", " ").title())
        y_label = elaboration.get("y_label", "Value")

        # Sort data if specified
        sort_by = elaboration.get("sort_by")
        if sort_by and data_rows:
            reverse = elaboration.get("sort_order", "asc") == "desc"
            try:
                data_rows = sorted(data_rows, key=lambda r: r.get(sort_by, 0), reverse=reverse)
            except (TypeError, KeyError):
                pass

        # If no y_fields, use the first numeric column
        if not y_fields and data_rows:
            for k, v in data_rows[0].items():
                if isinstance(v, (int, float)) and k != x_axis:
                    y_fields.append(k)

        # Parse width/height — percentage values default to 700px
        w_str = event.get("style_width", "700px")
        h_str = event.get("style_height", "400px")
        if "%" in w_str:
            width = 700  # percentage -> fixed for SVG viewBox
        else:
            w_num = w_str.replace("px", "").strip()
            width = int(w_num) if w_num.isdigit() else 700
        h_num = h_str.replace("px", "").strip()
        height = int(h_num) if h_num.isdigit() else 400

        colors = _get_colors(color_scheme, max(len(y_fields), len(data_rows)))

        # Generate SVG based on chart type
        if chart_type == "pie":
            value_field = y_fields[0] if y_fields else ""
            svg = _generate_pie_chart_svg(
                data_rows, x_axis, value_field, colors, title, width, height, show_legend,
            )
        elif chart_type == "line" or chart_type == "area":
            svg = _generate_line_chart_svg(
                data_rows, x_axis, y_fields, colors, title, x_label, y_label,
                width, height, show_legend, show_grid, show_values,
            )
        else:  # bar, dot, heatmap -> default to bar
            svg = _generate_bar_chart_svg(
                data_rows, x_axis, y_fields, colors, title, x_label, y_label,
                width, height, show_legend, show_grid, show_values, stacked,
            )

        # The code is the SVG source, the html wraps it
        chart_code = svg
        chart_html = f'<div class="chart-render" data-type="{chart_type}">{svg}</div>'

        logger.info(
            "Chart implemented: type=%s, title='%s', %d data rows, %d bytes SVG",
            chart_type, title, len(data_rows), len(svg),
        )

        return {"chart_code": chart_code, "chart_html": chart_html}


# =============================================================================
# ChartTester
# =============================================================================


@dataclass
class ChartTester:
    """Validates generated chart code for correctness."""

    name: str = "chart_tester"

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Event: {chart_code, chart_html, chart_type, data_rows}
        Returns: {test_result: {passed, checks, error?}}
        """
        chart_code = event.get("chart_code", "")
        chart_html = event.get("chart_html", "")
        chart_type = event.get("chart_type", "bar")
        data_rows = event.get("data_rows", [])

        checks: list[dict[str, Any]] = []

        # Check 1: Non-empty output
        has_content = bool(chart_code) and bool(chart_html)
        checks.append({"name": "has_content", "passed": has_content,
                        "detail": "Chart code and HTML must be non-empty"})

        # Check 2: Valid SVG structure
        has_svg = "<svg" in chart_code and "</svg>" in chart_code
        checks.append({"name": "valid_svg", "passed": has_svg,
                        "detail": "Output must contain valid SVG tags"})

        # Check 3: Contains data elements (rects for bar, polyline for line, path for pie)
        type_elements = {
            "bar": "<rect",
            "line": "<polyline",
            "pie": "<path",
            "area": "<polyline",
            "dot": "<circle",
        }
        expected_el = type_elements.get(chart_type, "<rect")
        has_data_els = expected_el in chart_code
        checks.append({"name": "has_data_elements", "passed": has_data_els,
                        "detail": f"SVG must contain {expected_el} elements for type '{chart_type}'"})

        # Check 4: Data row count matches visual elements
        if chart_type == "bar" and data_rows:
            rect_count = chart_code.count("<rect")
            # Bars + legend rects + grid
            min_expected = len(data_rows)
            has_enough = rect_count >= min_expected
            checks.append({"name": "data_coverage", "passed": has_enough,
                            "detail": f"Expected >= {min_expected} rect elements, found {rect_count}"})

        # Check 5: Title present
        has_title = "font-weight" in chart_code and "<text" in chart_code
        checks.append({"name": "has_title", "passed": has_title,
                        "detail": "Chart must contain a title text element"})

        all_passed = all(c["passed"] for c in checks)
        error = None
        if not all_passed:
            failed = [c for c in checks if not c["passed"]]
            error = "; ".join(c["detail"] for c in failed)

        result = {"passed": all_passed, "checks": checks}
        if error:
            result["error"] = error

        logger.info(
            "Chart test: passed=%s, checks=%d/%d",
            all_passed,
            sum(1 for c in checks if c["passed"]),
            len(checks),
        )

        return {"test_result": result}


# =============================================================================
# ChartVerifier
# =============================================================================


@dataclass
class ChartVerifier:
    """Visually verifies the rendered chart.

    In a production system, this would render the SVG to an image and
    use a vision model to evaluate the quality.  For this example,
    we perform heuristic checks on the SVG structure.
    """

    name: str = "chart_verifier"

    async def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Event: {chart_code, chart_html, chart_type, title, data_rows}
        Returns: {visual_feedback: 'approved' | 'revision instructions...'}
        """
        chart_code = event.get("chart_code", "")
        chart_type = event.get("chart_type", "bar")
        event.get("data_rows", [])
        event.get("title", "")

        issues: list[str] = []

        # Check proportionality: are bar heights somewhat varied?
        if chart_type == "bar":
            # Count rects that are not in legend/grid area
            import re
            heights = re.findall(r'height="(\d+\.?\d*)"', chart_code)
            if heights:
                h_values = [float(h) for h in heights if float(h) > 5]
                if h_values:
                    h_range = max(h_values) - min(h_values)
                    if h_range < 2 and len(h_values) > 1:
                        issues.append("Bars appear to have nearly identical heights - check data scaling")

        # Check that labels are present
        text_count = chart_code.count("<text")
        if text_count < 3:
            issues.append("Chart appears to have too few labels")

        # Check SVG size is reasonable
        if len(chart_code) < 100:
            issues.append("Chart SVG appears too small - may be empty or malformed")

        if len(chart_code) > 100_000:
            issues.append("Chart SVG is very large - consider simplifying")

        if issues:
            feedback = "Revision needed: " + "; ".join(issues)
        else:
            feedback = "approved"

        logger.info(
            "Chart visual verification: %s (%d issues)",
            "approved" if feedback == "approved" else "needs revision",
            len(issues),
        )

        return {
            "visual_feedback": feedback,
            "revision_instructions": "; ".join(issues) if issues else "",
        }
