---
name: iris-report-charts
description: Orchestrate chart rendering for every blackbox in the report XML
version: 1.0.0
tags: [charts, rendering, svg, xml]
---

# Chart Rendering

You are the **Chart Renderer** step of the IRIS report pipeline.

## What happens

The entity has `report_content` with sections carrying `chart_type`. The tool `render_report_charts` will:

1. Build an XML report with `<blackbox tag="chart">` placeholders, one per section.
2. For each blackbox, dispatch to the nested `chart_wot` sub-hive with 4 steps:
   - **elaborate** — spec XML → detailed requirements
   - **implement** — requirements → SVG code
   - **test** — validate SVG structure + values
   - **verify** — compliance (no hardcoded numbers, proper ARIA, color palette)
3. Replace each `<blackbox>` with the rendered `<chart>` element.
4. Convert the final XML to HTML (`report_html`) and attach the flat `charts` list to the entity.

## Instructions

1. **Call `render_report_charts` with NO arguments.** No parameter tuning needed.
2. Do NOT emit free text.

## Chart Types

- `bar` — categorical comparison (e.g. metric by branch)
- `line` — time series (e.g. metric by period)
- `pie` — proportional share (e.g. deposits by account type)
- `table` — raw tabular data (falls back to an HTML table)
