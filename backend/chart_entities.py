"""
Chart StatefulRecord — tracks each chart through the rendering pipeline.

Lifecycle states:
    elaboration     -> Understanding what chart to create from the blackbox spec
    implementation  -> Generating the chart HTML/SVG code
    test            -> Validating the chart code (syntax, data binding)
    verification    -> Visual check of the rendered chart output
    done            -> Chart successfully rendered and verified
    error           -> Unrecoverable error during any step

The chart WoT pipeline drives this entity through its states.
On verification failure, a feedback loop sends it back to elaboration
with new instructions from the visual checker.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from tachikoma.stateful.record import (
    Condition,
    StatefulRecord,
    TransitionDef,
    action,
    condition,
    on_enter,
    sr_init,
)

logger = logging.getLogger(__name__)

CHART_STATES = [
    "elaboration",
    "implementation",
    "test",
    "verification",
    "done",
    "revision",
    "error",
]


@sr_init(
    entity="chart",
    initial="elaboration",
    states=CHART_STATES,
)
class Chart(StatefulRecord):
    """Tracks a single chart through the rendering pipeline.

    Created from a <blackbox tag="chart"> element in the XML report.
    Contains all information needed to generate and verify the chart.

    Fields:
        chart_id: Matches the blackbox element's id attribute.
        report_id: Parent report ID.
        chart_type: Desired chart type (bar, line, pie, dot, area, heatmap).
        title: Chart title.
        description: What the chart should show.
        x_axis: Field name for X axis.
        y_axis: Field name(s) for Y axis (comma-separated).
        group_by: Grouping field for multi-series.
        stacked: Whether chart is stacked.
        color_scheme: Color palette name.
        data_columns: Available data columns.
        data_rows: Inline data as list of dicts.
        style_width: CSS width.
        style_height: CSS height.
        show_legend: Whether to show legend.
        show_grid: Whether to show grid.
        show_values: Whether to show values on chart.
        chart_html: Generated HTML/SVG code.
        chart_code: Source code used to generate the chart.
        test_result: Test pass/fail with details.
        visual_feedback: Feedback from visual verification.
        revision_instructions: Instructions for revision iteration.
        revision_count: Number of revision cycles.
        error_message: Error details if pipeline fails.
    """

    _transitions: ClassVar[list[TransitionDef]] = [
        # Happy path
        TransitionDef("elaboration", "implementation", condition="spec_ready"),
        TransitionDef("implementation", "test", condition="has_code"),
        TransitionDef("test", "verification", condition="test_passed"),
        TransitionDef("verification", "done", condition="visual_approved"),
        # Revision loop
        TransitionDef("verification", "revision", condition="needs_revision"),
        TransitionDef("revision", "elaboration"),
        # Error from any processing state
        TransitionDef(
            ["elaboration", "implementation", "test", "verification"],
            "error",
        ),
        # Test failure loops back to implementation
        TransitionDef("test", "implementation"),
    ]

    # -- Fields ---------------------------------------------------------------

    chart_id: str = ""
    report_id: str = ""
    chart_type: str = "bar"
    title: str = ""
    description: str = ""

    # Spec from blackbox
    x_axis: str = ""
    y_axis: str = ""
    group_by: str = ""
    stacked: bool = False
    color_scheme: str = "corporate-blue"

    # Data
    data_columns: list[str] = None  # type: ignore[assignment]
    data_rows: list[dict[str, Any]] = None  # type: ignore[assignment]

    # Style
    style_width: str = "100%"
    style_height: str = "400px"
    show_legend: bool = True
    show_grid: bool = True
    show_values: bool = False

    # Output
    chart_html: str = ""
    chart_code: str = ""

    # Pipeline state
    test_result: dict[str, Any] = None  # type: ignore[assignment]
    visual_feedback: str = ""
    revision_instructions: str = ""
    revision_count: int = 0
    error_message: str = ""

    # -- Conditions -----------------------------------------------------------

    @condition("spec_ready")
    def spec_ready(self) -> Condition:
        """Check that the chart spec has enough info to proceed."""
        return Condition.all_of(
            Condition.that(bool(self.chart_type), "Chart type is required"),
            Condition.that(bool(self.title), "Chart title is required"),
            Condition.that(
                self.data_rows is not None and len(self.data_rows) > 0,
                "Chart needs data rows",
            ),
        )

    @condition("has_code")
    def has_code(self) -> Condition:
        """Check that chart code was generated."""
        return Condition.all_of(
            Condition.that(bool(self.chart_code), "Chart code is missing"),
            Condition.that(bool(self.chart_html), "Chart HTML is missing"),
        )

    @condition("test_passed")
    def test_passed(self) -> Condition:
        """Check that the chart passed testing."""
        if self.test_result is None:
            return Condition(passed=False, reason="No test result")
        return Condition.that(
            self.test_result.get("passed", False),
            self.test_result.get("error", "Test did not pass"),
        )

    @condition("visual_approved")
    def visual_approved(self) -> Condition:
        """Check that visual verification passed."""
        return Condition.that(
            self.visual_feedback == "approved" or self.visual_feedback == "",
            f"Visual check feedback: {self.visual_feedback}",
        )

    @condition("needs_revision")
    def needs_revision(self) -> Condition:
        """Check if visual verification requires revision."""
        return Condition.all_of(
            Condition.that(
                self.visual_feedback not in ("approved", ""),
                "No revision needed",
            ),
            Condition.that(
                self.revision_count < 3,
                "Maximum revision count reached",
            ),
        )

    # -- Actions --------------------------------------------------------------

    @action("finalize_chart")
    async def finalize_chart(self) -> None:
        """Mark chart as complete."""
        logger.info(
            "Chart %s (%s) finalized: type=%s",
            self.chart_id,
            self.title,
            self.chart_type,
        )

    # -- Hooks ----------------------------------------------------------------

    @on_enter("elaboration")
    def on_elaboration(self) -> None:
        logger.info(
            "Chart %s entering elaboration (revision #%d)",
            self.chart_id,
            self.revision_count,
        )

    @on_enter("implementation")
    def on_implementation(self) -> None:
        logger.info("Chart %s entering implementation", self.chart_id)

    @on_enter("revision")
    def on_revision(self) -> None:
        self.revision_count += 1
        # Clear previous output for re-generation
        self.chart_html = ""
        self.chart_code = ""
        self.test_result = None
        logger.info(
            "Chart %s revision #%d: %s",
            self.chart_id,
            self.revision_count,
            self.visual_feedback,
        )

    @on_enter("error")
    def on_error(self) -> None:
        logger.error(
            "Chart %s error: %s",
            self.chart_id,
            self.error_message,
        )

    @on_enter("done")
    def on_done(self) -> None:
        logger.info(
            "Chart %s done: %d bytes of HTML",
            self.chart_id,
            len(self.chart_html),
        )

    # -- Factory: create from blackbox XML element ----------------------------

    @classmethod
    def from_blackbox(cls, blackbox_el: Any, report_id: str = "") -> Chart:
        """Create a Chart entity from a <blackbox tag='chart'> XML element.

        Args:
            blackbox_el: xml.etree.ElementTree.Element for the blackbox.
            report_id: Parent report ID.

        Returns:
            A new Chart entity in 'elaboration' state.
        """
        chart_id = blackbox_el.get("id", "")
        title = blackbox_el.get("title", "Untitled Chart")
        description = blackbox_el.get("description", "")

        # Parse chart-spec
        spec = blackbox_el.find("chart-spec")
        chart_type = spec.get("type", "bar") if spec is not None else "bar"
        x_axis = spec.get("x-axis", "") if spec is not None else ""
        y_axis = spec.get("y-axis", "") if spec is not None else ""
        group_by = spec.get("group-by", "") if spec is not None else ""
        stacked = (spec.get("stacked", "false") == "true") if spec is not None else False
        color_scheme = spec.get("color-scheme", "corporate-blue") if spec is not None else "corporate-blue"

        # Parse data rows
        data_ref = blackbox_el.find("data-ref")
        columns_str = data_ref.get("columns", "") if data_ref is not None else ""
        data_columns = [c.strip() for c in columns_str.split(",") if c.strip()] if columns_str else []

        data_rows = []
        for row_el in blackbox_el.findall("row"):
            row = {}
            for k, v in row_el.attrib.items():
                # Try to parse numbers
                try:
                    row[k] = float(v) if "." in v else int(v)
                except ValueError:
                    row[k] = v
            data_rows.append(row)

        # Parse style hints
        style = blackbox_el.find("style-hint")
        style_width = style.get("width", "100%") if style is not None else "100%"
        style_height = style.get("height", "400px") if style is not None else "400px"
        show_legend = (style.get("show-legend", "true") == "true") if style is not None else True
        show_grid = (style.get("show-grid", "true") == "true") if style is not None else True
        show_values = (style.get("show-values", "false") == "true") if style is not None else False

        return cls(
            chart_id=chart_id,
            report_id=report_id,
            chart_type=chart_type,
            title=title,
            description=description,
            x_axis=x_axis,
            y_axis=y_axis,
            group_by=group_by,
            stacked=stacked,
            color_scheme=color_scheme,
            data_columns=data_columns,
            data_rows=data_rows,
            style_width=style_width,
            style_height=style_height,
            show_legend=show_legend,
            show_grid=show_grid,
            show_values=show_values,
        )
