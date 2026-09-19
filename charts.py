"""Inline SVG charts.

Rendered server side so the app has no CDN dependency and works on a box with
no internet. Colours arrive already resolved from the validated categorical
palette; this module only does geometry.
"""
from __future__ import annotations

import json
import math
from html import escape

NICE_STEPS = (1, 2, 2.5, 5, 10)


def _nice_step(span: float, target_ticks: int = 5) -> float:
    if span <= 0:
        return 1.0
    raw = span / target_ticks
    magnitude = 10 ** math.floor(math.log10(raw))
    for mult in NICE_STEPS:
        if magnitude * mult >= raw:
            return magnitude * mult
    return magnitude * 10


def _axis_bounds(values: list[float], zero_base: bool = True) -> tuple[float, float, float]:
    """Y-axis range.

    Cumulative point totals start at zero. A bounded value series - judges'
    scores, which never go near zero - gets a padded window instead, otherwise
    the whole season is squashed into the top of the plot.
    """
    data_lo, data_hi = min(values), max(values)
    if zero_base:
        lo, hi = min(0.0, data_lo), max(1.0, data_hi)
    else:
        pad = (data_hi - data_lo or 1.0) * 0.25
        lo, hi = data_lo - pad, data_hi + pad
        if data_lo >= 0:
            lo = max(0.0, lo)

    step = _nice_step(hi - lo)
    lo = math.floor(lo / step) * step
    hi = math.ceil(hi / step) * step
    if hi <= lo:
        hi = lo + step
    return lo, hi, step


def _fmt(value: float) -> str:
    return f"{value:g}"


def cumulative_chart(
    series: list[dict], week_labels: list[str], zero_base: bool = True
) -> dict | None:
    """Multi-series line chart over the weeks of the season.

    ``series`` is a list of ``{"name", "color", "color_dark", "values"}``.
    Returns the SVG plus the JSON payload the hover layer needs, or ``None``
    when there is nothing to plot yet.
    """
    if not series or not week_labels:
        return None

    W, H = 720, 300
    L, R, T, B = 44, 128, 20, 40
    plot_w, plot_h = W - L - R, H - T - B

    all_values = [v for s in series for v in s["values"]]
    lo, hi, step = _axis_bounds(all_values, zero_base)

    n = len(week_labels)
    def x_of(i: int) -> float:
        return L + (plot_w / 2 if n == 1 else plot_w * i / (n - 1))

    def y_of(v: float) -> float:
        return T + plot_h - (v - lo) / (hi - lo) * plot_h

    parts: list[str] = [
        f'<svg viewBox="0 0 {W} {H}" role="img" class="chart-svg" '
        f'aria-label="Cumulative fantasy points by week">'
    ]

    # Gridlines + y ticks
    ticks: list[float] = []
    t = lo
    while t <= hi + 1e-9:
        ticks.append(round(t, 6))
        t += step
    for value in ticks:
        y = y_of(value)
        parts.append(
            f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{L + plot_w}" y2="{y:.1f}" />'
        )
        parts.append(
            f'<text class="tick" x="{L - 10}" y="{y + 4:.1f}" text-anchor="end">'
            f"{_fmt(value)}</text>"
        )

    # X ticks - thin them out once the season gets long.
    stride = max(1, n // 12)
    for i, label in enumerate(week_labels):
        if i % stride and i != n - 1:
            continue
        parts.append(
            f'<text class="tick" x="{x_of(i):.1f}" y="{T + plot_h + 22}" '
            f'text-anchor="middle">{escape(label)}</text>'
        )

    parts.append(
        f'<line class="axis" x1="{L}" y1="{T + plot_h}" '
        f'x2="{L + plot_w}" y2="{T + plot_h}" />'
    )

    # Hover crosshair, driven by the script in static/app.js
    parts.append(
        f'<line class="crosshair" x1="0" y1="{T}" x2="0" y2="{T + plot_h}" '
        f'style="opacity:0" />'
    )

    # Series: line, then marker ring, then marker.
    for idx, s in enumerate(series, start=1):
        pts = " ".join(
            f"{x_of(i):.1f},{y_of(v):.1f}" for i, v in enumerate(s["values"])
        )
        parts.append(
            f'<polyline class="series-line" style="stroke:var(--series-{idx})" '
            f'points="{pts}" />'
        )
        for i, v in enumerate(s["values"]):
            parts.append(
                f'<circle class="marker-ring" cx="{x_of(i):.1f}" cy="{y_of(v):.1f}" r="5" />'
                f'<circle class="marker" style="fill:var(--series-{idx})" '
                f'cx="{x_of(i):.1f}" cy="{y_of(v):.1f}" r="4" '
                f'data-series="{idx}" data-index="{i}" />'
            )

    # Direct labels at the end of each line, nudged apart when they collide.
    ends = sorted(
        ((y_of(s["values"][-1]), idx, s) for idx, s in enumerate(series, start=1)),
        key=lambda item: item[0],
    )
    last_y = -1e9
    for y, idx, s in ends:
        y = max(y, last_y + 17)
        last_y = y
        x = x_of(n - 1) + 14
        parts.append(
            f'<circle class="legend-dot" style="fill:var(--series-{idx})" '
            f'cx="{x + 4}" cy="{y - 4:.1f}" r="4" />'
        )
        parts.append(
            f'<text class="series-label" x="{x + 14}" y="{y:.1f}">'
            f'{escape(s["name"])} <tspan class="series-value">'
            f'{_fmt(s["values"][-1])}</tspan></text>'
        )

    parts.append("</svg>")

    payload = {
        "labels": week_labels,
        "geometry": {"left": L, "top": T, "width": plot_w, "height": plot_h, "vbWidth": W},
        "series": [{"name": s["name"], "values": s["values"]} for s in series],
    }
    return {"svg": "".join(parts), "data": json.dumps(payload)}


def sparkline(
    values: list[float],
    series_index: int,
    labels: list[str] | None = None,
    vmax: float | None = None,
) -> str:
    """A single-series cumulative sparkline for a couple or a team card.

    Pass ``vmax`` when several sparklines sit side by side, so they share a
    y-scale and a taller line really does mean more points.
    """
    if not values:
        return ""
    W, H, PAD = 160, 40, 5
    lo = min([0.0] + values)
    hi = max(values + [lo + 1] + ([vmax] if vmax is not None else []))
    n = len(values)

    def x_of(i: int) -> float:
        return PAD + (0 if n == 1 else (W - 2 * PAD) * i / (n - 1))

    def y_of(v: float) -> float:
        return H - PAD - (v - lo) / (hi - lo) * (H - 2 * PAD)

    pts = " ".join(f"{x_of(i):.1f},{y_of(v):.1f}" for i, v in enumerate(values))
    area = f"{PAD},{H - PAD} {pts} {x_of(n - 1):.1f},{H - PAD}"
    labels = labels or [f"W{i + 1}" for i in range(n)]
    title = ", ".join(f"{labels[i]}: {_fmt(v)}" for i, v in enumerate(values))

    return (
        f'<svg viewBox="0 0 {W} {H}" class="sparkline" role="img" '
        f'aria-label="Running points: {escape(title)}">'
        f"<title>{escape(title)}</title>"
        f'<polygon class="spark-area" style="fill:var(--series-{series_index})" '
        f'points="{area}" />'
        f'<polyline class="spark-line" style="stroke:var(--series-{series_index})" '
        f'points="{pts}" />'
        f'<circle class="marker-ring" cx="{x_of(n - 1):.1f}" cy="{y_of(values[-1]):.1f}" r="4.5" />'
        f'<circle class="marker" style="fill:var(--series-{series_index})" '
        f'cx="{x_of(n - 1):.1f}" cy="{y_of(values[-1]):.1f}" r="3.5" />'
        f"</svg>"
    )
