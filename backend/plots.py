"""Matplotlib PNGs for the slides, from the eval report JSON. Plan section 10.

Light surface, two or three categorical series in a fixed order, one axis per
panel, recessive grid, legend whenever there are two or more series.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e6e4df"
SERIES = {"on": "#2a78d6", "off": "#eb6834"}  # slot 1 blue, slot 2 orange
CHECKER_SERIES = {
    "speed_limit": "#2a78d6",
    "lane_change_gap": "#eb6834",
    "left_lane_passing": "#1baf7a",
}
CHECKER_LABEL = {
    "speed_limit": "Speed limit 25 m/s",
    "lane_change_gap": "Lane change gap 10 m",
    "left_lane_passing": "Left lane for passing",
    "lane_closed": "Lane closed",
}


def _style(ax: Any, title: str, ylabel: str, xlabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=TEXT, fontsize=11, pad=10)
    ax.set_ylabel(ylabel, color=TEXT_2, fontsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, color=TEXT_2, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=8, length=0)


def plot_before_after(before: dict[str, Any], after: dict[str, Any], path: Path) -> Path:
    """Violations and return per seed, shield off versus on, as grouped bars."""
    seeds = [e["seed"] for e in before["episodes"]]
    by_seed_on = {e["seed"]: e for e in after["episodes"]}
    x = range(len(seeds))
    width = 0.38
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.2), facecolor=SURFACE)
    for ax, key, ylabel, title in (
        (
            ax1,
            "violations_total",
            "violations per episode",
            "Rule violations per seed, shield off versus on",
        ),
        (ax2, "return", "task return", "Task return per seed, the cost of safety"),
    ):
        off_vals = [e[key] for e in before["episodes"]]
        on_vals = [by_seed_on[s][key] if s in by_seed_on else 0 for s in seeds]
        ax.bar(
            [i - width / 2 for i in x],
            off_vals,
            width,
            color=SERIES["off"],
            label="shield off",
            linewidth=0,
        )
        ax.bar(
            [i + width / 2 for i in x],
            on_vals,
            width,
            color=SERIES["on"],
            label="shield on",
            linewidth=0,
        )
        _style(ax, title, ylabel, "seed")
        ax.set_xticks(list(x), [str(s) for s in seeds])
        ax.legend(
            frameon=False,
            fontsize=8,
            labelcolor=TEXT_2,
            loc="upper left",
            bbox_to_anchor=(1.0, 1.0),
        )
    a_off, a_on = before["aggregate"], after["aggregate"]
    ax1.text(
        0.0,
        1.14,
        f"mean {a_off['violations_per_episode']:.1f} off, {a_on['violations_per_episode']:.1f} on   "
        f"crash rate {a_off['crash_rate']:.0%} off, {a_on['crash_rate']:.0%} on",
        transform=ax1.transAxes,
        color=TEXT_2,
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_tradeoff(sweep: list[dict[str, Any]], path: Path) -> Path:
    """Violations per episode against escalation rate, one point per threshold pair."""
    fig, ax = plt.subplots(figsize=(7.5, 4.6), facecolor=SURFACE)
    xs = [p["escalation_rate"] for p in sweep]
    ys = [p["violations_per_episode"] for p in sweep]
    ax.plot(xs, ys, color=SERIES["on"], linewidth=2, zorder=2)
    ax.scatter(xs, ys, s=46, color=SERIES["on"], edgecolor=SURFACE, linewidth=2, zorder=3)
    for p, x, y in zip(sweep, xs, ys, strict=True):
        ax.annotate(
            f"{p['t_allow']:.1f} / {p['t_block']:.1f}",
            (x, y),
            textcoords="offset points",
            xytext=(8, 6),
            fontsize=8,
            color=TEXT_2,
        )
    _style(
        ax,
        "Choosing the thresholds: violations against escalation rate",
        "violations per episode",
        "share of steps escalated to the operator",
    )
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_calibration(cal: dict[str, Any], path: Path) -> Path:
    """Reliability diagram: observed violation rate per bin of p, overall and per checker."""
    fig, (ax, ax_n) = plt.subplots(
        2,
        1,
        figsize=(7.5, 6.4),
        facecolor=SURFACE,
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    ax.plot([0, 1], [0, 1], color=GRID, linewidth=1, zorder=1)
    overall = cal["overall"]
    pts = [(b["mean_p"], b["observed"]) for b in overall["bins"] if b["count"]]
    ax.plot(
        [p for p, _ in pts],
        [o for _, o in pts],
        color=TEXT_2,
        linewidth=2,
        linestyle="--",
        label=f"all rules, ECE {overall['ece']:.3f}",
        zorder=2,
    )
    for name, rel in cal["by_checker"].items():
        color = CHECKER_SERIES.get(name)
        if color is None or rel["n"] == 0:
            continue
        pts = [(b["mean_p"], b["observed"]) for b in rel["bins"] if b["count"]]
        ax.plot(
            [p for p, _ in pts],
            [o for _, o in pts],
            color=color,
            linewidth=2,
            marker="o",
            markersize=5,
            markeredgecolor=SURFACE,
            label=f"{CHECKER_LABEL.get(name, name)}, ECE {rel['ece']:.3f}",
            zorder=3,
        )
    _style(
        ax, f"Is p(violation) calibrated? {overall['n']} labeled checks", "observed violation rate"
    )
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT_2, loc="upper left")
    counts = [b["count"] for b in overall["bins"]]
    centers = [(b["lo"] + b["hi"]) / 2 for b in overall["bins"]]
    ax_n.bar(centers, counts, width=0.09, color=GRID, linewidth=0)
    _style(ax_n, "", "checks per bin", "Jev p(violation)")
    ax_n.set_xlim(0, 1)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return path
