"""Shield Wall Balance & Soak Report Runner (Step 5).

Plays 200 headless matches per fighter pair on HIGH difficulty with shields ON vs OFF
to prove that Shield Wall is balanced and not overpowered:
1. Win rate of every matchup with and without shields (no matchup moves > 10pp).
2. Average shields per round and break rate.
3. Average match length (must not increase by > 20%).
4. Share of time spent behind a shield (must stay < 25% for every fighter).

Also supports running a 1,000-match soak test with shields ON (`--soak 1000`).

Usage:
  uv run python -m backend.data.shield_balance
  uv run python -m backend.data.shield_balance --matches 200 --soak 1000
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import random
import sys
import time
from typing import Any, Dict, List, Tuple

from backend.ai.adapter import observation_for
from backend.ai.crimson import CrimsonAgent
from backend.ai.difficulty import DifficultyWrapper
from backend.ai.golden import GoldenAgent
from backend.ai.shadow import ShadowAgent
from backend.ai.steel import SteelAgent
from backend.engine.constants import ARENA_WIDTH
from backend.engine.rules import ModeRules
from backend.engine.step import make_initial_state, new_round, step

FIGHTER_CLASSES = {
    "Crimson": CrimsonAgent,
    "Steel": SteelAgent,
    "Shadow": ShadowAgent,
    "Golden": GoldenAgent,
}
FIGHTER_NAMES = ["Crimson", "Steel", "Shadow", "Golden"]
DIFFICULTIES = ["LOW", "MEDIUM", "HIGH", "HELL"]


def _play_single_balance_match(args: Tuple[str, str, str, bool, int]) -> Dict[str, Any]:
    """Play one headless match and gather shield wall telemetry."""
    c1, c2, diff, enable_shield, seed = args
    rules = ModeRules.classic(enable_shield_wall=enable_shield)

    a1 = FIGHTER_CLASSES[c1](player=1, difficulty=diff, seed=seed * 2)
    a2 = FIGHTER_CLASSES[c2](player=2, difficulty=diff, seed=seed * 2 + 1)

    state = make_initial_state(c1, c2, rules=rules, seed=seed)
    a1.reset()
    a2.reset()

    total_frames = 0
    rounds_played = 1
    p1_raised = 0
    p2_raised = 0
    p1_broken = 0
    p2_broken = 0
    p1_time_behind = 0
    p2_time_behind = 0
    stuck_violations = 0
    crashes = 0

    try:
        while not state.match_over:
            obs1 = observation_for(state, 1)
            obs2 = observation_for(state, 2)

            act1, _ = a1.decide(obs1)
            act2, _ = a2.decide(obs2)

            new_state = step(state, act1, act2)
            total_frames += 1

            # Check no fighter stuck inside any shield while grounded
            if enable_shield:
                for f in (new_state.fighter1, new_state.fighter2):
                    if not f.in_air:
                        for owner_f in (new_state.fighter1, new_state.fighter2):
                            sw = owner_f.shield_wall
                            if sw is not None and abs(f.x - sw.x) < (sw.width / 2.0 - 4.0):
                                stuck_violations += 1

            a1.observe(obs1, act1, act2)
            a2.observe(obs2, act2, act1)
            state = new_state

            if state.round_over:
                p1_raised += state.fighter1.shield_walls_raised
                p2_raised += state.fighter2.shield_walls_raised
                p1_broken += state.fighter1.shield_walls_broken
                p2_broken += state.fighter2.shield_walls_broken
                p1_time_behind += state.fighter1.shield_time_behind_frames
                p2_time_behind += state.fighter2.shield_time_behind_frames

                if not state.match_over:
                    rounds_played += 1
                    state = new_round(state)
                    a1.reset()
                    a2.reset()
    except Exception:
        crashes = 1

    return {
        "c1": c1,
        "c2": c2,
        "enable_shield": enable_shield,
        "result": state.match_result,
        "total_frames": total_frames,
        "rounds_played": rounds_played,
        "p1_raised": p1_raised,
        "p2_raised": p2_raised,
        "p1_broken": p1_broken,
        "p2_broken": p2_broken,
        "p1_time_behind": p1_time_behind,
        "p2_time_behind": p2_time_behind,
        "stuck_violations": stuck_violations,
        "crashes": crashes,
    }


def run_balance_benchmark(matches_per_pair: int = 200, workers: int | None = None) -> Dict[str, Any]:
    """Run matches_per_pair matches for all 6 unique pairs with Shields OFF vs ON."""
    num_workers = workers or max(1, (os.cpu_count() or 4) - 1)
    pairs = []
    for i in range(len(FIGHTER_NAMES)):
        for j in range(i + 1, len(FIGHTER_NAMES)):
            pairs.append((FIGHTER_NAMES[i], FIGHTER_NAMES[j]))

    print("=" * 72, flush=True)
    print(f"  SHIELD WALL BALANCE REPORT ({matches_per_pair} matches/pair on HIGH, {num_workers} workers)", flush=True)
    print("=" * 72, flush=True)

    tasks = []
    for c1, c2 in pairs:
        for m_idx in range(matches_per_pair):
            seed = 50000 + m_idx + (FIGHTER_NAMES.index(c1) * 1000) + (FIGHTER_NAMES.index(c2) * 100)
            tasks.append((c1, c2, "HIGH", False, seed))
            tasks.append((c1, c2, "HIGH", True, seed))

    results: List[Dict[str, Any]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(_play_single_balance_match, t) for t in tasks]
        for idx, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if idx % 200 == 0 or idx == len(tasks):
                print(f"  Progress: {idx}/{len(tasks)} matches completed ({time.perf_counter()-t0:.1f}s)", flush=True)

    # Aggregate statistics
    summary_lines = [
        "# Shield Wall Balance Report",
        "",
        f"Evaluated **{matches_per_pair} matches per matchup** on `HIGH` difficulty (Shields OFF vs Shields ON).",
        "",
        "## 1. Matchup Win Rate Comparison (P1 Win %)",
        "| Matchup | Shields OFF (P1 Win%) | Shields ON (P1 Win%) | Delta (pp) | Status |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    max_delta_pp = 0.0
    total_frames_off = 0
    total_frames_on = 0
    count_off = 0
    count_on = 0

    fighter_frames_behind = {name: 0 for name in FIGHTER_NAMES}
    fighter_frames_total = {name: 0 for name in FIGHTER_NAMES}
    total_rounds_on = 0
    total_shields_raised = 0
    total_shields_broken = 0

    for c1, c2 in pairs:
        off_matches = [r for r in results if r["c1"] == c1 and r["c2"] == c2 and not r["enable_shield"]]
        on_matches = [r for r in results if r["c1"] == c1 and r["c2"] == c2 and r["enable_shield"]]

        wr_off = 100.0 * sum(1 for r in off_matches if r["result"] == "p1") / len(off_matches)
        wr_on = 100.0 * sum(1 for r in on_matches if r["result"] == "p1") / len(on_matches)
        delta = wr_on - wr_off
        max_delta_pp = max(max_delta_pp, abs(delta))
        status = "OK" if abs(delta) <= 10.0 else "FAIL (>10pp)"

        summary_lines.append(f"| {c1} vs {c2} | {wr_off:.1f}% | {wr_on:.1f}% | {delta:+.1f} pp | {status} |")

        total_frames_off += sum(r["total_frames"] for r in off_matches)
        count_off += len(off_matches)
        total_frames_on += sum(r["total_frames"] for r in on_matches)
        count_on += len(on_matches)

        for r in on_matches:
            total_rounds_on += r["rounds_played"]
            total_shields_raised += (r["p1_raised"] + r["p2_raised"])
            total_shields_broken += (r["p1_broken"] + r["p2_broken"])
            fighter_frames_behind[c1] += r["p1_time_behind"]
            fighter_frames_total[c1] += r["total_frames"]
            fighter_frames_behind[c2] += r["p2_time_behind"]
            fighter_frames_total[c2] += r["total_frames"]

    avg_len_off = (total_frames_off / count_off) / 60.0
    avg_len_on = (total_frames_on / count_on) / 60.0
    len_increase_pct = 100.0 * (avg_len_on - avg_len_off) / max(0.01, avg_len_off)

    avg_shields_per_round = total_shields_raised / max(1, total_rounds_on)
    break_rate_pct = 100.0 * total_shields_broken / max(1, total_shields_raised)

    summary_lines.extend([
        "",
        "## 2. Pacing & Shield Usage Metrics",
        f"- **Average Match Length (OFF)**: {avg_len_off:.2f} s",
        f"- **Average Match Length (ON)**: {avg_len_on:.2f} s ({len_increase_pct:+.1f}% change — Target: <= +20%)",
        f"- **Average Shields per Round**: {avg_shields_per_round:.2f}",
        f"- **Shield Break Rate**: {break_rate_pct:.1f}% ({total_shields_broken} broken / {total_shields_raised} raised)",
        "",
        "## 3. Time Spent Behind Shield (Target: < 25% per fighter)",
        "| Fighter | Time Behind Shield | Status |",
        "| :--- | :---: | :---: |",
    ])

    max_shield_share = 0.0
    for name in FIGHTER_NAMES:
        share = 100.0 * fighter_frames_behind[name] / max(1, fighter_frames_total[name])
        max_shield_share = max(max_shield_share, share)
        st = "OK" if share < 25.0 else "FAIL (>=25%)"
        summary_lines.append(f"| {name} | {share:.2f}% | {st} |")

    passed = (max_delta_pp <= 10.0) and (len_increase_pct <= 20.0) and (max_shield_share < 25.0)
    summary_lines.extend([
        "",
        f"## Final Balance Verdict: **{'PASSED' if passed else 'NEEDS TUNING'}**",
    ])

    report_text = "\n".join(summary_lines)
    os.makedirs("docs/results", exist_ok=True)
    out_path = os.path.join("docs", "results", "shield_balance.md")
    with open(out_path, "w") as f:
        f.write(report_text)

    print("\n" + report_text, flush=True)
    print(f"\n[SAVED] Balance report written to {out_path}", flush=True)
    return {"passed": passed, "max_delta_pp": max_delta_pp, "len_increase_pct": len_increase_pct, "max_shield_share": max_shield_share}


def run_shield_soak(matches: int = 1000, workers: int | None = None) -> bool:
    """Run 1,000 random matches with Shield Wall ON to verify zero crashes and zero stuck states."""
    num_workers = workers or max(1, (os.cpu_count() or 4) - 1)
    print("=" * 72, flush=True)
    print(f"  SHIELD WALL SOAK TEST: {matches} RANDOM MATCHES (Workers: {num_workers})", flush=True)
    print("=" * 72, flush=True)

    rng = random.Random(9000)
    tasks = []
    for i in range(matches):
        c1 = rng.choice(FIGHTER_NAMES)
        c2 = rng.choice(FIGHTER_NAMES)
        diff = rng.choice(DIFFICULTIES)
        tasks.append((c1, c2, diff, True, 80000 + i))

    crashes = 0
    stuck = 0
    t0 = time.perf_counter()

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(_play_single_balance_match, t) for t in tasks]
        for idx, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            crashes += res["crashes"]
            stuck += res["stuck_violations"]
            if idx % 200 == 0 or idx == matches:
                print(f"  Soak Progress: {idx}/{matches} matches ({time.perf_counter()-t0:.1f}s)", flush=True)

    print("-" * 72, flush=True)
    print(f"  Crashes          : {crashes} (Target: 0)", flush=True)
    print(f"  Stuck Violations : {stuck} (Target: 0)", flush=True)
    print(f"  Result           : {'PASSED' if crashes == 0 and stuck == 0 else 'FAILED'}", flush=True)
    print("-" * 72, flush=True)
    return crashes == 0 and stuck == 0


def main():
    parser = argparse.ArgumentParser(description="Shield Wall Balance Benchmark & Soak Suite")
    parser.add_argument("--matches", type=int, default=200, help="Matches per pair for balance report")
    parser.add_argument("--soak", type=int, default=0, help="Run N random soak matches with shields ON")
    parser.add_argument("--workers", type=int, default=None, help="Parallel worker processes")
    args = parser.parse_args()

    bal = run_balance_benchmark(matches_per_pair=args.matches, workers=args.workers)
    soak_ok = True
    if args.soak > 0:
        soak_ok = run_shield_soak(matches=args.soak, workers=args.workers)

    if not bal["passed"] or not soak_ok:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
