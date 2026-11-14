"""Generate charts for fight statistics and save them to docs/results/.

Uses matplotlib to create:
  1. Elo rating bar chart for all fighters.
  2. Win rate heatmap (fighter vs fighter).
  3. Difficulty progression chart (win rate at each difficulty level).
"""

import os

from backend.data.statistics import (
    compute_elo,
    difficulty_ranking,
    run_round_robin,
    FIGHTER_NAMES,
)

# Where to save charts
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "results")


def _ensure_results_dir():
    """Create the results directory if it doesn't exist."""
    os.makedirs(RESULTS_DIR, exist_ok=True)


def generate_elo_chart(results=None, output_path=None):
    """Create a bar chart of Elo ratings for all fighters.

    results: output of run_round_robin(). If None, runs a quick tournament.
    output_path: where to save the image. Default: docs/results/elo_ratings.png
    """
    import matplotlib
    matplotlib.use("Agg")  # no GUI needed
    import matplotlib.pyplot as plt

    _ensure_results_dir()

    if results is None:
        results = run_round_robin(matches_per_pair=5)

    elo = compute_elo(results)

    # Sort fighters by Elo rating
    sorted_fighters = sorted(elo.keys(), key=lambda f: elo[f], reverse=True)
    ratings = [elo[f] for f in sorted_fighters]

    # Colours matching the fighter costumes
    colours = {
        "Crimson": "#B41E1E",
        "Steel": "#64686E",
        "Shadow": "#28143C",
        "Golden": "#C8AA32",
    }
    bar_colours = [colours.get(f, "#888888") for f in sorted_fighters]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(sorted_fighters, ratings, color=bar_colours, edgecolor="white")

    # Add value labels on the bars
    for bar, rating in zip(bars, ratings):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                f"{rating:.0f}", ha="center", va="bottom", fontsize=12)

    ax.set_ylabel("Elo Rating")
    ax.set_title("Fighter Elo Ratings")
    ax.set_ylim(bottom=min(ratings) - 50, top=max(ratings) + 50)
    ax.grid(axis="y", alpha=0.3)

    if output_path is None:
        output_path = os.path.join(RESULTS_DIR, "elo_ratings.png")
    fig.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return output_path


def generate_winrate_heatmap(results=None, output_path=None):
    """Create a heatmap of win rates (fighter vs fighter).

    Each cell shows how often the row fighter beats the column fighter.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    _ensure_results_dir()

    if results is None:
        results = run_round_robin(matches_per_pair=5)

    fighters = FIGHTER_NAMES
    n = len(fighters)
    # Build a 2D win rate table
    rates = [[0.5] * n for _ in range(n)]  # diagonal = 0.5

    for r in results:
        i = fighters.index(r["fighter1"]) if r["fighter1"] in fighters else -1
        j = fighters.index(r["fighter2"]) if r["fighter2"] in fighters else -1
        if i < 0 or j < 0:
            continue
        total = r["wins1"] + r["wins2"] + r["draws"]
        if total == 0:
            continue
        rates[i][j] = r["wins1"] / total
        rates[j][i] = r["wins2"] / total

    fig, ax = plt.subplots(figsize=(6, 5))
    data = [[rates[i][j] for j in range(n)] for i in range(n)]
    im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=1)

    # Labels
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(fighters)
    ax.set_yticklabels(fighters)
    ax.set_title("Win Rates (Row vs Column)")

    # Add text inside cells
    for i in range(n):
        for j in range(n):
            text = f"{data[i][j]:.0%}"
            colour = "white" if data[i][j] < 0.3 or data[i][j] > 0.7 else "black"
            ax.text(j, i, text, ha="center", va="center", color=colour, fontsize=11)

    fig.colorbar(im, ax=ax, label="Win Rate")

    if output_path is None:
        output_path = os.path.join(RESULTS_DIR, "winrate_heatmap.png")
    fig.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return output_path


def generate_difficulty_chart(fighter_name="Crimson", output_path=None):
    """Create a line chart showing win rate at each difficulty level.

    Runs the fighter against RandomAgent at LOW, MEDIUM, HIGH, HELL.
    Should show an increasing trend (harder difficulty = higher win rate).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _ensure_results_dir()

    rates = difficulty_ranking(fighter_name, matches_per_difficulty=10)
    difficulties = ["LOW", "MEDIUM", "HIGH", "HELL"]
    values = [rates[d] for d in difficulties]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(difficulties, values, "o-", color="#B41E1E", linewidth=2, markersize=8)

    # Fill area under the curve
    ax.fill_between(difficulties, values, alpha=0.2, color="#B41E1E")

    # Add value labels
    for i, (d, v) in enumerate(zip(difficulties, values)):
        ax.text(i, v + 0.02, f"{v:.0%}", ha="center", fontsize=11)

    ax.set_ylabel("Win Rate vs Random")
    ax.set_title(f"{fighter_name}: Win Rate by Difficulty")
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", alpha=0.3)

    if output_path is None:
        output_path = os.path.join(RESULTS_DIR, f"difficulty_{fighter_name.lower()}.png")
    fig.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return output_path


def generate_all_charts():
    """Generate all charts and return a list of file paths."""
    _ensure_results_dir()

    # Run one round-robin and reuse results for Elo and heatmap
    results = run_round_robin(matches_per_pair=5)

    paths = []
    paths.append(generate_elo_chart(results))
    paths.append(generate_winrate_heatmap(results))

    # Difficulty chart for each fighter
    for name in FIGHTER_NAMES:
        paths.append(generate_difficulty_chart(name))

    return paths
