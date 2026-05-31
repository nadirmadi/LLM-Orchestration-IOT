"""
plot_benchmark.py — Generate 3 publication-quality charts from
benchmark_results.csv.

Produces:
  /data/chart_discovery_time.pdf
  /data/chart_kickoff_time.pdf
  /data/chart_tool_calls.pdf

Usage:
    python -m scripts.plot_benchmark
    # or from Docker:
    docker compose --profile dockered-ollama run --rm crew \
        python -m scripts.plot_benchmark
"""

import csv
import os
from collections import defaultdict

# ── Try matplotlib; if not installed, install it ──
try:
    import matplotlib
    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
except ImportError:
    print("Installing matplotlib...")
    os.system(f"{__import__('sys').executable} -m pip install "
              "matplotlib --break-system-packages -q")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

CSV_PATH = "/data/benchmark_results.csv"
OUT_DIR = "/data"


def load_data():
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Group by n_devices
    grouped = defaultdict(list)
    for r in rows:
        n = int(r["n_devices"])
        grouped[n].append({
            "discovery_time_s": float(r["discovery_time_s"]),
            "kickoff_time_s": float(r["kickoff_time_s"]),
            "tool_calls": int(r["tool_calls"]),
        })
    return grouped


def compute_stats(grouped, key):
    """Returns (sizes, means, mins, maxs) for the given key."""
    sizes = sorted(grouped.keys())
    means, mins, maxs = [], [], []
    for n in sizes:
        vals = [r[key] for r in grouped[n] if r[key] > 0]
        if vals:
            means.append(sum(vals) / len(vals))
            mins.append(min(vals))
            maxs.append(max(vals))
        else:
            means.append(0)
            mins.append(0)
            maxs.append(0)
    return sizes, means, mins, maxs


def style_ax(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel, fontsize=12, fontweight="medium")
    ax.set_ylabel(ylabel, fontsize=12, fontweight="medium")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=10)


def plot_chart(sizes, means, mins, maxs, ylabel, title, filename,
               color="#1a6fdf"):
    fig, ax = plt.subplots(figsize=(7, 4.5))

    # Error bars (min-max range)
    yerr_low = [m - lo for m, lo in zip(means, mins)]
    yerr_high = [hi - m for m, hi in zip(means, maxs)]

    ax.errorbar(sizes, means, yerr=[yerr_low, yerr_high],
                fmt="o-", color=color, capsize=5, capthick=1.5,
                linewidth=2, markersize=7, markerfacecolor="white",
                markeredgewidth=2, markeredgecolor=color)

    # Fill between min and max
    ax.fill_between(sizes, mins, maxs, alpha=0.1, color=color)

    # Annotate each point with its mean value
    for x, y in zip(sizes, means):
        ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points",
                    xytext=(0, 12), ha="center", fontsize=9,
                    color=color, fontweight="medium")

    style_ax(ax, "Nombre de dispositifs", ylabel, title)

    # X-axis: use exact sizes
    ax.set_xticks(sizes)
    ax.set_xticklabels([str(s) for s in sizes])

    fig.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def main():
    print("Loading benchmark data...")
    grouped = load_data()

    print(f"  Found data for sizes: {sorted(grouped.keys())}")
    print()

    # ── Chart 1: Discovery time ──
    sizes, means, mins, maxs = compute_stats(grouped, "discovery_time_s")
    plot_chart(sizes, means, mins, maxs,
               ylabel="Temps de discovery (s)",
               title="Temps de mesh discovery en fonction\n"
                     "du nombre de dispositifs",
               filename="chart_discovery_time.pdf",
               color="#1a6fdf")

    # ── Chart 2: Kickoff time ──
    sizes, means, mins, maxs = compute_stats(grouped, "kickoff_time_s")
    plot_chart(sizes, means, mins, maxs,
               ylabel="Temps de kickoff (s)",
               title="Temps de kickoff complet (intent → réponse)\n"
                     "en fonction du nombre de dispositifs",
               filename="chart_kickoff_time.pdf",
               color="#e6550d")

    # ── Chart 3: Tool calls ──
    sizes, means, mins, maxs = compute_stats(grouped, "tool_calls")
    plot_chart(sizes, means, mins, maxs,
               ylabel="Nombre d'appels d'outils MCP",
               title="Nombre d'appels d'outils MCP par kickoff\n"
                     "en fonction du nombre de dispositifs",
               filename="chart_tool_calls.pdf",
               color="#2ca02c")

    print("\nDone! Charts saved in /data/")
    print("Copy them to your LaTeX images/ folder:")
    print("  cp /data/chart_*.pdf images/")


if __name__ == "__main__":
    main()
