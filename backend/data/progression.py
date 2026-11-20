"""Progression, economy, and reward systems for Arena-AI.

Handles:
- Match coin rewards with detailed itemized breakdowns.
- Character leveling (costs and stat multiplier curves).
- 18 trophies with in-game detection and persistence.
- Per-battle and global missions with coin rewards.
"""

from typing import Any, Dict, List, Optional, Tuple
from backend.data.results_db import results_db

# ----------------------------------------------------------------------
# Reward Configuration
# ----------------------------------------------------------------------
REWARD_CONFIG = {
    "win_base": 150,
    "loss_base": 40,
    "round_win": 35,
    "damage_scale": 120.0,      # damage_dealt_p1 (0.0 - 2.0) * 120
    "combo_scale": 12,          # longest_combo * 12
    "block_scale": 4,           # blocks_p1 * 4
    "flawless_round": 75,       # per round won with 0 damage taken
    "perfect_match": 150,       # entire match won without damage
    "speed_bonus_max": 80,      # bonus for fast wins (under 45s)
    "difficulty_mult": {
        "LOW": 1.0,
        "MEDIUM": 1.25,
        "HIGH": 1.5,
        "HELL": 2.0,
    },
    "level_diff_bonus": 15,     # per opponent level above player
}

MAX_LEVEL = 20


def get_upgrade_cost(current_level: int) -> int:
    """Calculate the coin cost to advance from current_level to current_level + 1."""
    if current_level >= MAX_LEVEL:
        return 0
    return int(100 * (current_level ** 1.4))


def get_level_multipliers(level: int) -> Dict[str, float]:
    """Calculate stat multipliers for a warrior at a given level (1 to 20).

    Stat scaling is modest and balanced:
    - health_mult: divides incoming damage (+5% effective HP per level)
    - damage_mult: scales outgoing attack damage (+3% per level)
    - speed_mult: scales walk speed (+1% per level)
    - block_mult: reduces chip damage when blocking (+2% per level)
    """
    lvl = max(1, min(MAX_LEVEL, level))
    step = lvl - 1
    return {
        "health_mult": round(1.0 + step * 0.05, 3),
        "damage_mult": round(1.0 + step * 0.03, 3),
        "speed_mult": round(1.0 + step * 0.01, 3),
        "block_mult": round(1.0 + step * 0.02, 3),
    }


def calculate_match_rewards(
    stats: Dict[str, Any],
    player_level: int = 1,
    opponent_level: int = 1,
) -> Dict[str, Any]:
    """Calculate itemized coin rewards for the human player after a match."""
    is_win = (stats.get("winner_side") == 1)
    rounds_won = stats.get("rounds_p1", 0)
    damage_dealt = stats.get("damage_dealt_p1", 0.0)
    longest_combo = stats.get("longest_combo_p1", 0)
    blocks = stats.get("blocks_p1", 0)
    damage_taken = stats.get("damage_dealt_p2", 0.0)
    duration = stats.get("duration_s", 60.0)
    difficulty = stats.get("p2_difficulty", "LOW")

    diff_mult = REWARD_CONFIG["difficulty_mult"].get(difficulty, 1.0)
    breakdown: List[Tuple[str, int]] = []

    # 1. Base outcome
    base_val = REWARD_CONFIG["win_base"] if is_win else REWARD_CONFIG["loss_base"]
    breakdown.append(("Victory Base" if is_win else "Consolation Base", base_val))

    # 2. Rounds won
    if rounds_won > 0:
        r_val = rounds_won * REWARD_CONFIG["round_win"]
        breakdown.append((f"Rounds Won ({rounds_won}x)", r_val))

    # 3. Damage dealt
    dmg_val = int(damage_dealt * REWARD_CONFIG["damage_scale"])
    if dmg_val > 0:
        breakdown.append(("Damage Dealt", dmg_val))

    # 4. Combo bonus
    if longest_combo >= 2:
        combo_val = longest_combo * REWARD_CONFIG["combo_scale"]
        breakdown.append((f"Best Combo ({longest_combo}-Hit)", combo_val))

    # 5. Defense bonus
    if blocks > 0:
        blk_val = blocks * REWARD_CONFIG["block_scale"]
        breakdown.append((f"Guards & Parries ({blocks}x)", blk_val))

    # 6. Flawless & Perfect
    flawless_rounds = stats.get("flawless_rounds_p1", 0)
    if is_win and damage_taken <= 0.001:
        breakdown.append(("Perfect Match Victory!", REWARD_CONFIG["perfect_match"]))
    elif flawless_rounds > 0:
        breakdown.append((f"Flawless Round ({flawless_rounds}x)", flawless_rounds * REWARD_CONFIG["flawless_round"]))

    # 7. Speed bonus
    if is_win and duration < 45.0:
        speed_factor = max(0.0, (45.0 - duration) / 45.0)
        spd_val = int(REWARD_CONFIG["speed_bonus_max"] * speed_factor)
        if spd_val > 0:
            breakdown.append(("Speedy Finish", spd_val))

    # 8. Opponent level differential
    if opponent_level > player_level:
        lvl_bonus = (opponent_level - player_level) * REWARD_CONFIG["level_diff_bonus"]
        breakdown.append((f"Underdog Bonus (+{opponent_level - player_level} Lvls)", lvl_bonus))

    subtotal = sum(v for _, v in breakdown)
    total = int(subtotal * diff_mult)

    if diff_mult > 1.0:
        breakdown.append((f"Difficulty Multiplier ({difficulty} x{diff_mult})", total - subtotal))

    return {
        "total_coins": total,
        "breakdown": breakdown,
        "is_win": is_win,
    }


# ----------------------------------------------------------------------
# Trophies Definition
# ----------------------------------------------------------------------
ALL_TROPHIES = [
    {"id": "first_blood", "name": "First Blood", "desc": "Land your first strike in combat."},
    {"id": "flawless_round", "name": "Flawless Round", "desc": "Win a round taking zero damage."},
    {"id": "combo_5", "name": "Combo Adept", "desc": "Land a 5-hit combo in a match."},
    {"id": "combo_8", "name": "Combo Master", "desc": "Land an 8-hit combo in a match."},
    {"id": "iron_wall", "name": "Iron Wall", "desc": "Block 15 attacks in a single match."},
    {"id": "untouchable", "name": "Untouchable", "desc": "Win a match without dropping a single round."},
    {"id": "comeback_king", "name": "Comeback King", "desc": "Win a round from under 15% health."},
    {"id": "super_finish", "name": "Limit Break", "desc": "Finish off an opponent with a Super attack."},
    {"id": "speed_demon", "name": "Swift Justice", "desc": "Win a match in under 30 seconds."},
    {"id": "defeat_crimson", "name": "Crimson Slayer", "desc": "Defeat Crimson in combat."},
    {"id": "defeat_steel", "name": "Steel Breaker", "desc": "Defeat Steel in combat."},
    {"id": "defeat_shadow", "name": "Light in the Dark", "desc": "Defeat Shadow in combat."},
    {"id": "defeat_golden", "name": "Gold Standard", "desc": "Defeat Golden in combat."},
    {"id": "campaign_start", "name": "Tournament Challenger", "desc": "Win Battle 1 of the Campaign."},
    {"id": "campaign_champ", "name": "Grand Champion", "desc": "Complete all 8 battles of the Campaign."},
    {"id": "lvl_5", "name": "Seasoned Fighter", "desc": "Upgrade any warrior to Level 5."},
    {"id": "lvl_10", "name": "Master Warrior", "desc": "Upgrade any warrior to Level 10."},
    {"id": "big_spender", "name": "High Roller", "desc": "Spend 1,000 coins on warrior upgrades."},
]


def check_match_trophies(stats: Dict[str, Any], player_id: int) -> List[Dict[str, str]]:
    """Evaluate trophies unlocked by the match results. Returns freshly unlocked list."""
    unlocked_now: List[Dict[str, str]] = []
    unlocked_ids = results_db.get_unlocked_trophy_ids(player_id)

    def _award(t_id: str):
        if t_id not in unlocked_ids:
            if results_db.unlock_trophy(player_id, t_id):
                for t in ALL_TROPHIES:
                    if t["id"] == t_id:
                        unlocked_now.append(t)
                        unlocked_ids.add(t_id)
                        break

    if stats.get("hits_landed_p1", 0) > 0:
        _award("first_blood")
    if stats.get("flawless_rounds_p1", 0) > 0:
        _award("flawless_round")
    if stats.get("longest_combo_p1", 0) >= 5:
        _award("combo_5")
    if stats.get("longest_combo_p1", 0) >= 8:
        _award("combo_8")
    if stats.get("blocks_p1", 0) >= 15:
        _award("iron_wall")

    is_win = (stats.get("winner_side") == 1)
    if is_win:
        if stats.get("rounds_p2", 0) == 0:
            _award("untouchable")
        if stats.get("duration_s", 60.0) < 30.0:
            _award("speed_demon")
        p2_char = stats.get("p2_character", "")
        if p2_char == "Crimson":
            _award("defeat_crimson")
        elif p2_char == "Steel":
            _award("defeat_steel")
        elif p2_char == "Shadow":
            _award("defeat_shadow")
        elif p2_char == "Golden":
            _award("defeat_golden")
        if stats.get("comeback_p1", False):
            _award("comeback_king")
        if stats.get("super_ko_p1", False):
            _award("super_finish")

    # Check level & spender trophies
    prog = results_db.get_or_create_progress(player_id)
    max_lvl = max(
        prog.get("crimson_level", 1),
        prog.get("steel_level", 1),
        prog.get("shadow_level", 1),
        prog.get("golden_level", 1),
    )
    if max_lvl >= 5:
        _award("lvl_5")
    if max_lvl >= 10:
        _award("lvl_10")
    if prog.get("total_coins_spent", 0) >= 1000:
        _award("big_spender")

    return unlocked_now


# ----------------------------------------------------------------------
# Missions Definition
# ----------------------------------------------------------------------
ALL_MISSIONS = [
    # Global persistent missions
    {"id": "win_3_matches", "name": "Victory Road", "desc": "Win 3 matches across any mode", "target": 3, "reward": 150, "type": "global"},
    {"id": "block_30_attacks", "name": "Solid Guard", "desc": "Block 30 incoming attacks total", "target": 30, "reward": 120, "type": "global"},
    {"id": "land_15_specials", "name": "Specialist", "desc": "Perform 15 special attacks total", "target": 15, "reward": 140, "type": "global"},
    {"id": "reach_level_5", "name": "Growing Stronger", "desc": "Upgrade any warrior to Level 5", "target": 5, "reward": 200, "type": "global"},
    # Match-specific objectives
    {"id": "flawless_round_obj", "name": "Flawless Strike", "desc": "Win a round taking zero damage", "target": 1, "reward": 100, "type": "battle"},
    {"id": "combo_5_obj", "name": "Fluid Assault", "desc": "Land a 5-hit combo in battle", "target": 1, "reward": 75, "type": "battle"},
    {"id": "no_block_win", "name": "All In", "desc": "Win a match without blocking once", "target": 1, "reward": 90, "type": "battle"},
    {"id": "speed_win_obj", "name": "Blitzkrieg", "desc": "Win a match in under 40 seconds", "target": 1, "reward": 110, "type": "battle"},
]


def check_match_missions(stats: Dict[str, Any], player_id: int) -> List[Dict[str, Any]]:
    """Update progress for missions and return list of newly completed missions."""
    newly_completed: List[Dict[str, Any]] = []
    is_win = (stats.get("winner_side") == 1)

    # 1. Global: Win 3 matches
    if is_win:
        is_comp, is_new = results_db.update_mission(player_id, "win_3_matches", 1, 3)
        if is_new:
            newly_completed.append(_find_mission("win_3_matches"))

    # 2. Global: Block 30 attacks
    blocks = stats.get("blocks_p1", 0)
    if blocks > 0:
        is_comp, is_new = results_db.update_mission(player_id, "block_30_attacks", blocks, 30)
        if is_new:
            newly_completed.append(_find_mission("block_30_attacks"))

    # 3. Global: Specials performed
    specials = stats.get("specials_p1", 0)
    if specials > 0:
        is_comp, is_new = results_db.update_mission(player_id, "land_15_specials", specials, 15)
        if is_new:
            newly_completed.append(_find_mission("land_15_specials"))

    # 4. Global: Level 5
    prog = results_db.get_or_create_progress(player_id)
    max_lvl = max(
        prog.get("crimson_level", 1),
        prog.get("steel_level", 1),
        prog.get("shadow_level", 1),
        prog.get("golden_level", 1),
    )
    is_comp, is_new = results_db.update_mission(player_id, "reach_level_5", max_lvl, 5)
    if is_new:
        newly_completed.append(_find_mission("reach_level_5"))

    # 5. Battle: Flawless round
    if stats.get("flawless_rounds_p1", 0) > 0:
        is_comp, is_new = results_db.update_mission(player_id, "flawless_round_obj", 1, 1)
        if is_new:
            newly_completed.append(_find_mission("flawless_round_obj"))

    # 6. Battle: 5-hit combo
    if stats.get("longest_combo_p1", 0) >= 5:
        is_comp, is_new = results_db.update_mission(player_id, "combo_5_obj", 1, 1)
        if is_new:
            newly_completed.append(_find_mission("combo_5_obj"))

    # 7. Battle: No-block win
    if is_win and stats.get("blocks_p1", 0) == 0:
        is_comp, is_new = results_db.update_mission(player_id, "no_block_win", 1, 1)
        if is_new:
            newly_completed.append(_find_mission("no_block_win"))

    # 8. Battle: Speed win
    if is_win and stats.get("duration_s", 60.0) < 40.0:
        is_comp, is_new = results_db.update_mission(player_id, "speed_win_obj", 1, 1)
        if is_new:
            newly_completed.append(_find_mission("speed_win_obj"))

    return [m for m in newly_completed if m is not None]


def _find_mission(mission_id: str) -> Optional[Dict[str, Any]]:
    for m in ALL_MISSIONS:
        if m["id"] == mission_id:
            return m
    return None
