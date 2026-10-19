import argparse
import json
import math
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "templates"
DEFAULT_DATA = ROOT / "weekly_data.json"
DEFAULT_OUTPUT = ROOT / "index.html"
KPI_FORMATS = {"integer", "euro_compact"}


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_text(mapping: dict[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.{key} must be a non-empty string")
    return value


def require_number(value: Any, path: str, *, allow_none: bool = False) -> float | int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{path} must be a finite number" + (" or null" if allow_none else ""))
    if value < 0:
        raise ValueError(f"{path} must not be negative")
    return value


def validate_data(data: Any) -> dict[str, Any]:
    data = require_mapping(data, "data")
    report = require_mapping(data.get("report"), "report")
    for key in ("organization", "week_label", "deck"):
        require_text(report, key, "report")

    summary = require_mapping(data.get("summary"), "summary")
    require_text(summary, "heading", "summary")
    facts = summary.get("facts")
    if not isinstance(facts, list):
        raise ValueError("summary.facts must be a list")
    for index, fact in enumerate(facts):
        fact = require_mapping(fact, f"summary.facts[{index}]")
        require_text(fact, "lead", f"summary.facts[{index}]")
        if not isinstance(fact.get("detail", ""), str):
            raise ValueError(f"summary.facts[{index}].detail must be text")
        if not isinstance(fact.get("attention", False), bool):
            raise ValueError(f"summary.facts[{index}].attention must be true or false")

    kpis = data.get("kpis")
    if not isinstance(kpis, list) or len(kpis) != 3:
        raise ValueError("kpis must contain exactly three entries to match the report layout")
    for index, kpi in enumerate(kpis):
        path = f"kpis[{index}]"
        kpi = require_mapping(kpi, path)
        require_text(kpi, "label", path)
        if kpi.get("tone", "") not in ("", "pipeline", "risk"):
            raise ValueError(f"{path}.tone must be empty, pipeline, or risk")
        if kpi.get("format") not in KPI_FORMATS:
            raise ValueError(f"{path}.format must be one of {sorted(KPI_FORMATS)}")
        if kpi.get("change_format") not in ("percent", "difference"):
            raise ValueError(f"{path}.change_format must be percent or difference")
        require_number(kpi.get("value"), f"{path}.value", allow_none=True)
        require_number(kpi.get("previous"), f"{path}.previous", allow_none=True)
        if kpi.get("format") == "integer":
            for key in ("value", "previous"):
                value = kpi.get(key)
                if value is not None and not float(value).is_integer():
                    raise ValueError(f"{path}.{key} must be a whole number")
        if kpi.get("format") == "euro_compact" and kpi.get("change_format") == "difference":
            raise ValueError(f"{path} cannot use difference formatting for euro_compact values")

    analysis = require_mapping(data.get("analysis"), "analysis")
    for key in (
        "heading", "pipeline_title", "pipeline_subtitle", "pipeline_caption",
        "status_title", "status_caption",
    ):
        require_text(analysis, key, "analysis")
    series = analysis.get("pipeline_series", [])
    if not isinstance(series, list):
        raise ValueError("analysis.pipeline_series must be a list")
    if series and len(series) < 2:
        raise ValueError("analysis.pipeline_series must contain at least two points")
    for index, point in enumerate(series):
        point = require_mapping(point, f"analysis.pipeline_series[{index}]")
        require_text(point, "week", f"analysis.pipeline_series[{index}]")
        require_number(point.get("value"), f"analysis.pipeline_series[{index}].value")

    counts = analysis.get("status_counts")
    if counts is not None:
        counts = require_mapping(counts, "analysis.status_counts")
        for key in ("on_track", "at_risk", "overdue"):
            value = require_number(counts.get(key), f"analysis.status_counts.{key}", allow_none=True)
            if value is not None and not float(value).is_integer():
                raise ValueError(f"analysis.status_counts.{key} must be a whole number")

    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        raise ValueError("recommendations must be a list")
    for index, recommendation in enumerate(recommendations):
        recommendation = require_mapping(recommendation, f"recommendations[{index}]")
        require_text(recommendation, "title", f"recommendations[{index}]")
        require_text(recommendation, "body", f"recommendations[{index}]")
    if recommendations:
        require_text(data, "recommendations_heading", "data")

    return data


def format_value(value: float | int | None, value_format: str) -> str:
    if value is None:
        return "Not available"
    if value_format == "integer":
        return f"{value:,.0f}"
    if value_format == "euro_compact":
        amount = value / 1000
        return f"€{amount:,.0f}k" if amount.is_integer() else f"€{amount:,.1f}k"
    raise ValueError(f"Unsupported value format: {value_format}")


def format_thousands(value: float | int) -> str:
    formatted = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"
    return f"€{formatted}k"


def prepare_kpis(kpis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for kpi in kpis:
        current = kpi.get("value")
        previous = kpi.get("previous")
        display_value = format_value(current, kpi["format"])
        if current is None or previous is None:
            change = "No comparison data"
        elif kpi["change_format"] == "percent":
            if previous == 0:
                change = "No comparison data"
            else:
                percentage = round((current - previous) / previous * 100)
                arrow = "↑" if percentage > 0 else "↓" if percentage < 0 else "→"
                change = f"{arrow} {abs(percentage)}% · {format_value(previous, kpi['format'])} last week"
        else:
            difference = current - previous
            arrow = "↑" if difference > 0 else "↓" if difference < 0 else "→"
            suffix = " project" if abs(difference) == 1 else " projects"
            change = f"{arrow} {abs(difference):,.0f}{suffix} · {format_value(previous, kpi['format'])} last week"
        prepared.append({**kpi, "display_value": display_value, "change": change})
    return prepared


def prepare_pipeline_chart(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not series:
        return None
    left, right, top, bottom = 48, 618, 26, 173
    max_value = max(float(point["value"]) for point in series)
    axis_max = max(10, math.ceil(max_value / 10) * 10)
    points = []
    for index, point in enumerate(series):
        x = round(left + (right - left) * index / (len(series) - 1))
        y = round(bottom - (bottom - top) * float(point["value"]) / axis_max)
        points.append({"x": x, "y": y, "week": point["week"], "value": point["value"]})
    line_path = "M" + " L".join(f"{point['x']} {point['y']}" for point in points)
    area_path = f"{line_path} L{right} {bottom} L{left} {bottom} Z"
    ticks = [
        {"y": round(top + (bottom - top) * index / 4), "label": format_thousands(axis_max * (4 - index) / 4)}
        for index in range(4)
    ]
    ticks.append({"y": bottom, "label": "€0k"})
    final = points[-1]
    accessible_label = f"Sales pipeline ranges from {format_thousands(points[0]['value'])} in {points[0]['week']} to {format_thousands(final['value'])} in {final['week']}."
    return {
        "points": points,
        "ticks": ticks,
        "line_path": line_path,
        "area_path": area_path,
        "last_point": final,
        "last_value_label": format_thousands(final["value"]),
        "accessible_label": accessible_label,
    }


def prepare_status_chart(analysis: dict[str, Any]) -> dict[str, Any] | None:
    counts = analysis.get("status_counts")
    labels = (("on_track", "On track", "", "#635bff"), ("at_risk", "At risk", "risk", "#bc7a40"), ("overdue", "Overdue", "overdue", "#b7483d"))
    if not counts or any(counts.get(key) is None for key, *_ in labels):
        return None
    values = [int(counts[key]) for key, *_ in labels]
    total = sum(values)
    if total == 0:
        return None
    gap = 6
    usable_width = 640 - gap * (len(values) - 1)
    items = []
    x = 0
    for (key, label, tone, color), value in zip(labels, values):
        width = usable_width * value / total
        items.append({"label": label, "tone": tone, "color": color, "value": value, "x": round(x, 2), "width": round(width, 2), "center": round(x + width / 2, 2)})
        x += width + gap
    accessible_label = f"{values[0]} projects on track, {values[1]} at risk, and {values[2]} overdue."
    return {"items": items, "accessible_label": accessible_label, "subtitle": f"{total} active client projects"}


def build_context(data: dict[str, Any]) -> dict[str, Any]:
    data = validate_data(data)
    analysis = data["analysis"]
    return {
        **data,
        "kpis": prepare_kpis(data["kpis"]),
        "pipeline_chart": prepare_pipeline_chart(analysis.get("pipeline_series", [])),
        "status_chart": prepare_status_chart(analysis),
        "recommendations": data.get("recommendations", []),
        "recommendations_heading": data.get("recommendations_heading", "Weekly priorities"),
    }


def render_report(data: dict[str, Any]) -> str:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("weekly_brief.html")
    return template.render(**build_context(data))


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Founder Weekly Brief from a JSON data file.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Path to the report JSON data")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path for the rendered HTML report")
    args = parser.parse_args()
    with args.data.open(encoding="utf-8") as data_file:
        data = json.load(data_file)
    html = render_report(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Rendered {args.output}")


if __name__ == "__main__":
    main()