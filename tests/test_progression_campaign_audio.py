"""Unit tests for Progression, Economy, Campaign, Audio, and Tutorial systems.

Verifies:
- Procedural audio generation, sound dictionary, volume scaling, and mute toggle.
- Coin reward calculations with itemized breakdown.
- Level upgrade costs and stat multiplier curves.
- Backward compatibility: health_mult=1.0, damage_mult=1.0, regen_enabled=False by default.
- Health regeneration behavior when enabled (recovers after 2s without damage, resets on hit).
- Campaign 8-battle configuration, difficulty escalation, and lore interpolation.
- Trophy unlocks and mission completion/claiming with SQLite persistence.
"""

import os
import tempfile
import pytest
import pygame

from backend.ai.actions import Action
from backend.data.campaign import CAMPAIGN_BATTLES, format_story_paragraphs, get_battle
from backend.data.progression import (
    ALL_MISSIONS,
    ALL_TROPHIES,
    MAX_LEVEL,
    REWARD_CONFIG,
    calculate_match_rewards,
    check_match_missions,
    check_match_trophies,
    get_level_multipliers,
    get_upgrade_cost,
)
from backend.data.results_db import ResultsDB
from backend.engine.constants import REGEN_DELAY_FRAMES, REGEN_RATE_PER_FRAME
from backend.engine.combat import apply_damage
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step
from frontend.audio import AudioManager


@pytest.fixture(autouse=True)
def ensure_pygame_display_init():
    """Ensure pygame display and font are initialized in headless mode."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1280, 720))
    pygame.event.clear()
    yield
    pygame.event.clear()


@pytest.fixture
def mem_db():
    """Isolated temporary SQLite database for progression tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_progression.db")
        db = ResultsDB(db_path=db_path)
        yield db


# ----------------------------------------------------------------------
# 1. Audio Tests
# ----------------------------------------------------------------------
def test_audio_manager_synthesis_and_volume():
    """Verify procedural audio generates without errors and volume updates work."""
    mgr = AudioManager(sample_rate=22050)
    # Check key sounds exist
    expected_sounds = [
        "menu_hover", "menu_select", "menu_back", "menu_error",
        "whoosh_light", "whoosh_heavy", "hit_light", "hit_heavy",
        "block", "special", "super", "jump", "land", "dash", "throw",
        "round_start", "fight", "ko", "round_win", "match_win", "match_lose",
        "coin", "level_up", "trophy", "mission_complete",
        "music_menu", "music_fight",
    ]
    for name in expected_sounds:
        assert name in mgr._sounds, f"Missing synthesized sound: {name}"

    # Volume and mute adjustments
    mgr.update_volume(master=0.7, sfx=0.5, music=0.4, muted=False)
    assert mgr.master_volume == 0.7
    assert mgr.sfx_volume == 0.5
    assert mgr.music_volume == 0.4
    assert not mgr.is_muted

    mgr.play_sfx("coin")
    mgr.play_music("music_menu")
    mgr.stop_music()


# ----------------------------------------------------------------------
# 2. Progression & Reward Math Tests
# ----------------------------------------------------------------------
def test_upgrade_costs_and_stat_multipliers():
    """Verify upgrade costs grow with level and stat multiplier curve is balanced."""
    # Level 1 cost
    assert get_upgrade_cost(1) == 100
    # Higher levels cost more
    assert get_upgrade_cost(2) > get_upgrade_cost(1)
    assert get_upgrade_cost(5) > get_upgrade_cost(2)
    # At MAX_LEVEL, cost is 0
    assert get_upgrade_cost(MAX_LEVEL) == 0

    # Level 1 multipliers (must be baseline 1.0)
    lvl1 = get_level_multipliers(1)
    assert lvl1["health_mult"] == 1.0
    assert lvl1["damage_mult"] == 1.0
    assert lvl1["speed_mult"] == 1.0
    assert lvl1["block_mult"] == 1.0

    # Level 5 multipliers (+5% HP, +3% dmg, +1% spd, +2% blk per level)
    lvl5 = get_level_multipliers(5)
    assert lvl5["health_mult"] == 1.20
    assert lvl5["damage_mult"] == 1.12
    assert lvl5["speed_mult"] == 1.04
    assert lvl5["block_mult"] == 1.08


def test_calculate_match_rewards():
    """Verify reward calculation itemized breakdown and bonuses."""
    win_stats = {
        "winner_side": 1,
        "rounds_p1": 2,
        "rounds_p2": 0,
        "damage_dealt_p1": 1.5,
        "damage_dealt_p2": 0.2,
        "longest_combo_p1": 5,
        "blocks_p1": 4,
        "flawless_rounds_p1": 1,
        "duration_s": 25.0,
        "p2_difficulty": "HIGH",
    }
    rewards = calculate_match_rewards(win_stats, player_level=2, opponent_level=4)
    assert rewards["is_win"] is True
    assert rewards["total_coins"] > 0
    # Check that breakdown contains itemized bonuses
    labels = [lbl for lbl, _ in rewards["breakdown"]]
    assert any("Victory" in l for l in labels)
    assert any("Rounds Won" in l for l in labels)
    assert any("Damage Dealt" in l for l in labels)
    assert any("Best Combo" in l for l in labels)
    assert any("Guards" in l for l in labels)
    assert any("Flawless" in l for l in labels)
    assert any("Speedy" in l for l in labels)
    assert any("Underdog" in l for l in labels)
    assert any("Difficulty" in l for l in labels)


# ----------------------------------------------------------------------
# 3. Engine Backward Compatibility & Health Regen Tests
# ----------------------------------------------------------------------
def test_engine_backward_compatibility_defaults():
    """Verify state defaults ensure classic/simulation behavior is 100% unaltered."""
    state = make_initial_state("Golden", "Crimson")
    f1 = state.fighter1
    f2 = state.fighter2

    assert f1.level == 1
    assert f1.health_mult == 1.0
    assert f1.damage_mult == 1.0
    assert f1.speed_mult == 1.0
    assert f1.block_mult == 1.0
    assert f1.regen_enabled is False
    assert f1.no_hit_timer == 0

    assert f2.level == 1
    assert f2.health_mult == 1.0
    assert f2.damage_mult == 1.0
    assert f2.speed_mult == 1.0
    assert f2.block_mult == 1.0
    assert f2.regen_enabled is False


def test_health_regeneration_behavior():
    """Verify health regeneration triggers only after 2s without damage or while blocking."""
    # Create state with regen enabled for P1
    state = make_initial_state("Golden", "Crimson", p1_regen=True)
    f1 = state.fighter1
    f1.health = 0.50
    f1.no_hit_timer = 0

    # Step for 60 frames (1 second): under 120 frames delay, not blocking -> no regen
    for _ in range(60):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.health == pytest.approx(0.50, abs=1e-5)

    # Step past 120 frames (2 seconds): regen starts
    for _ in range(65):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.health > 0.50

    # When active blocking, regen works even before 120 frames
    state2 = make_initial_state("Golden", "Crimson", p1_regen=True)
    state2.fighter1.health = 0.60
    state2.fighter1.no_hit_timer = 10
    state2 = step(state2, Action.BLOCK, Action.IDLE)
    assert state2.fighter1.health > 0.60

    # Taking damage resets no_hit_timer to 0
    apply_damage(state.fighter1, 0.10, is_blocking=False, blocked_damage_ratio=1.0)
    assert state.fighter1.no_hit_timer == 0


def test_damage_and_health_multipliers():
    """Verify damage multiplier expands outgoing damage and health multiplier scales defense."""
    defender = FighterState(health=1.0, health_mult=1.0)
    attacker_normal = FighterState(damage_mult=1.0)
    attacker_buffed = FighterState(damage_mult=1.5)

    # Normal attack
    dmg1 = apply_damage(defender, 0.10, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker_normal)
    assert dmg1 == pytest.approx(0.10)

    # Buffed attacker (+50% damage)
    defender2 = FighterState(health=1.0, health_mult=1.0)
    dmg2 = apply_damage(defender2, 0.10, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker_buffed)
    assert dmg2 == pytest.approx(0.15)

    # High health multiplier (e.g. 2.0x effective HP pool -> takes half incoming damage)
    defender_tank = FighterState(health=1.0, health_mult=2.0)
    dmg3 = apply_damage(defender_tank, 0.10, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker_normal)
    assert dmg3 == pytest.approx(0.05)


# ----------------------------------------------------------------------
# 4. Campaign Battles Definition Tests
# ----------------------------------------------------------------------
def test_campaign_battles_progression():
    """Verify 8 battles with escalating difficulties and valid story text."""
    assert len(CAMPAIGN_BATTLES) == 8

    # Battle 1 starts at LOW difficulty
    b1 = get_battle(1)
    assert b1["difficulty"] == "LOW"
    assert b1["opponent"] == "Crimson"

    # Battle 8 is the final boss at HELL difficulty
    b8 = get_battle(8)
    assert b8["difficulty"] == "HELL"
    assert "FINAL BOSS" in b8["title"]

    # Story interpolation
    paras = format_story_paragraphs(b1, "Shadow")
    assert any("Shadow" in p for p in paras)


# ----------------------------------------------------------------------
# 5. Database, Trophies & Missions Tests
# ----------------------------------------------------------------------
def test_db_progression_currency_and_levels(mem_db):
    """Verify coin transactions, warrior levels, and campaign saves."""
    p_id = mem_db.get_or_create_player("Hero")

    # Add & spend coins
    assert mem_db.add_coins(p_id, 500) == 500
    assert mem_db.spend_coins(p_id, 200) is True
    assert mem_db.get_or_create_progress(p_id)["coins"] == 300
    assert mem_db.spend_coins(p_id, 1000) is False  # insufficient

    # Character levels
    assert mem_db.get_character_level(p_id, "Crimson") == 1
    mem_db.set_character_level(p_id, "Crimson", 5)
    assert mem_db.get_character_level(p_id, "Crimson") == 5

    # Campaign progress
    mem_db.save_campaign_battle_result(p_id, battle_id=1, stars=3)
    camp = mem_db.get_campaign_progress(p_id)
    assert camp["unlocked_battle"] == 2
    assert 1 in camp["completed_battles"]
    assert camp["stars"]["1"] == 3


def test_trophies_and_missions_evaluation(mem_db):
    """Verify trophies and missions evaluate and persist properly."""
    from backend.data.results_db import results_db

    # Monkeypatch results_db for testing progression functions
    import backend.data.progression as prog_mod
    orig_db = prog_mod.results_db
    prog_mod.results_db = mem_db

    try:
        p_id = mem_db.get_or_create_player("TestFighter")

        match_stats = {
            "winner_side": 1,
            "hits_landed_p1": 5,
            "flawless_rounds_p1": 1,
            "longest_combo_p1": 6,
            "blocks_p1": 16,
            "rounds_p2": 0,
            "duration_s": 22.0,
            "p2_character": "Steel",
            "specials_p1": 3,
        }

        # Check trophies
        unlocked = check_match_trophies(match_stats, p_id)
        u_ids = {t["id"] for t in unlocked}
        assert "first_blood" in u_ids
        assert "flawless_round" in u_ids
        assert "combo_5" in u_ids
        assert "iron_wall" in u_ids
        assert "untouchable" in u_ids
        assert "defeat_steel" in u_ids

        # Check missions
        completed_m = check_match_missions(match_stats, p_id)
        m_ids = {m["id"] for m in completed_m}
        assert "flawless_round_obj" in m_ids
        assert "combo_5_obj" in m_ids

        # Claim mission
        assert mem_db.claim_mission(p_id, "flawless_round_obj") is True
        assert mem_db.claim_mission(p_id, "flawless_round_obj") is False  # Already claimed

    finally:
        prog_mod.results_db = orig_db


# ----------------------------------------------------------------------
# 6. Module Import Delegation & Tutorial/Story Headless Tests
# ----------------------------------------------------------------------
def test_module_attribute_delegation():
    """Verify that importing singleton modules directly never causes AttributeError."""
    from frontend import assets as assets_mod
    assert hasattr(assets_mod, "get_arena")
    assert hasattr(assets_mod, "get_portrait")
    surf = assets_mod.get_arena("arena_moonlit_bamboo", size=(100, 100))
    assert surf is not None

    from frontend import audio as audio_mod
    assert hasattr(audio_mod, "play_sfx")
    assert hasattr(audio_mod, "play_music")

    from backend.data import results_db as rdb_mod
    assert hasattr(rdb_mod, "get_character_level")
    assert hasattr(rdb_mod, "get_campaign_progress")


def test_camera_state_compatibility():
    """Verify CameraState provides both get_offset and present methods."""
    from frontend.camera_effects import CameraState
    camera = CameraState(1280, 720)
    camera.update(300, 600, 500)
    ox, oy = camera.get_offset()
    assert isinstance(ox, float)
    assert isinstance(oy, float)

    src = pygame.Surface((1280, 720))
    dest = pygame.Surface((1280, 720))
    camera.present(src, dest)


def test_tutorial_dummy_agent():
    """Verify DummyAgent functions as a valid Agent for both step and decide."""
    from frontend.tutorial import DummyAgent
    from backend.ai.actions import Action

    dummy = DummyAgent("Steel")
    assert dummy.player == 2
    assert dummy.current_mode == "STAND"

    # choose_action
    act, scores = dummy.choose_action(None)
    assert act == Action.IDLE

    # cycle modes
    mode2 = dummy.cycle_mode()
    assert mode2 == "CROUCH"
    act2, _ = dummy.choose_action(None)
    assert act2 == Action.CROUCH

    # decide method contract
    act_dec, _ = dummy.decide(None)
    assert isinstance(act_dec, Action)


def test_tutorial_and_story_screens_headless():
    """Verify run_tutorial and story_screen execute without throwing exceptions."""
    surface = pygame.Surface((1280, 720))
    clock = pygame.time.Clock()

    from frontend.tutorial import run_tutorial
    from frontend.campaign_screens import story_screen
    from backend.data.campaign import get_battle

    # Test run_tutorial with simulated ESC key
    pygame.event.clear()
    for _ in range(5):
        pygame.event.post(pygame.event.Event(pygame.NOEVENT))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    run_tutorial(surface, clock, "Golden")

    # Test story_screen with simulated ESC key
    pygame.event.clear()
    for _ in range(5):
        pygame.event.post(pygame.event.Event(pygame.NOEVENT))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    res = story_screen(surface, clock, get_battle(1), "Crimson")
    assert res is True

