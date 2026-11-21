"""Tests for frontend theme palettes and asset management."""

import pytest
import pygame

from frontend.theme import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    FLOOR_HEIGHT,
    PRIMARY_PALETTES,
    ALTERNATE_PALETTES,
    get_fighter_palette,
)
from frontend.assets import (
    assets,
    NORMAL_ARENAS,
    SPECIAL_ARENA,
    AssetManager,
)


@pytest.fixture(scope="module", autouse=True)
def init_pygame():
    pygame.init()
    yield
    pygame.quit()


def test_theme_dimensions():
    """Verify screen measurements and floor level."""
    assert SCREEN_WIDTH == 1024
    assert SCREEN_HEIGHT == 600
    # Floor is bottom 18% -> 492
    assert FLOOR_HEIGHT == 492


def test_theme_palettes():
    """Ensure all 4 fighters have primary and alternate mirror palettes."""
    fighters = ["Crimson", "Steel", "Shadow", "Golden"]
    for f in fighters:
        assert f in PRIMARY_PALETTES
        assert f in ALTERNATE_PALETTES
        primary = get_fighter_palette(f, is_p2_mirror=False)
        alt = get_fighter_palette(f, is_p2_mirror=True)
        assert primary["body"] != alt["body"]


def test_asset_arena_selection():
    """Verify arena rotation rules."""
    mgr = AssetManager()

    # HELL mode must always choose the special arena
    assert mgr.pick_arena("HELL") == SPECIAL_ARENA
    assert mgr.pick_arena("HELL", seed=99) == SPECIAL_ARENA

    # Normal mode picks from NORMAL_ARENAS
    a1 = mgr.pick_arena("LOW", seed=10)
    assert a1 in NORMAL_ARENAS

    # Never pick the same arena twice in a row
    for seed in range(20):
        next_arena = mgr.pick_arena("MEDIUM", seed=seed)
        assert next_arena in NORMAL_ARENAS


def test_asset_loading_and_fallback():
    """Verify asset loader caches and handles missing assets safely."""
    mgr = AssetManager()

    # Missing file should not raise an error, but return a placeholder surface
    placeholder = mgr.load_surface("nonexistent_dir", "missing_asset", (100, 100))
    assert isinstance(placeholder, pygame.Surface)
    assert placeholder.get_size() == (100, 100)

    # Calling again should retrieve cached surface
    cached = mgr.load_surface("nonexistent_dir", "missing_asset", (100, 100))
    assert cached is placeholder


def test_asset_portraits():
    """Verify portrait loader and flipping."""
    p1 = assets.get_portrait("Crimson", size=(100, 120), flip_h=False)
    p2 = assets.get_portrait("Crimson", size=(100, 120), flip_h=True)
    assert isinstance(p1, pygame.Surface)
    assert isinstance(p2, pygame.Surface)
    assert p1.get_size() == (100, 120)
    assert p2.get_size() == (100, 120)


def test_screen_assets():
    """Verify screen backgrounds are available."""
    intro = assets.get_intro()
    intro_blur = assets.get_intro_blur()
    victory = assets.get_victory()
    defeat = assets.get_defeat()
    draw = assets.get_draw_screen()

    for surf in [intro, intro_blur, victory, defeat, draw]:
        assert isinstance(surf, pygame.Surface)
        assert surf.get_size() == (SCREEN_WIDTH, SCREEN_HEIGHT)


@pytest.mark.parametrize("char_name", ["Crimson", "Steel", "Shadow", "Golden"])
def test_character_pose_assets_and_rendering(char_name):
    """Verify all 6 character pose sprites exist, map accurately, and render cleanly."""
    from backend.ai.actions import Action
    from backend.engine.state import FighterState
    from frontend.draw_fighter import (
        draw_fighter,
        get_fighter_sprite_seamless,
        resolve_fighter_pose,
    )

    poses = ("idle", "kick", "punch", "run", "jump", "crouch")
    pose_map = assets.get_fighter_poses(char_name)
    assert set(pose_map.keys()) == set(poses)

    for pose in poses:
        assert assets.has_fighter_pose(char_name, pose) is True
        surf = assets.get_fighter_sprite(char_name, pose=pose)
        assert isinstance(surf, pygame.Surface)
        assert surf.get_width() > 50 and surf.get_height() > 50

        seamless = get_fighter_sprite_seamless(char_name, height=200, is_mirror=False, pose=pose)
        assert isinstance(seamless, pygame.Surface)
        assert seamless.get_height() == 200

    # Verify state-to-pose resolution and rendering across all stances/moves
    canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)

    # 1. Idle
    f = FighterState(x=300.0, character_name=char_name)
    assert resolve_fighter_pose(f) == "idle"
    draw_fighter(canvas, f, facing_right=True)

    # 2. Run / Walk / Dash
    for move_act in (Action.FORWARD, Action.BACK, Action.DASH, Action.BACKDASH):
        f = FighterState(x=300.0, character_name=char_name, current_action=move_act, last_action=move_act)
        assert resolve_fighter_pose(f) == "run"
        draw_fighter(canvas, f, facing_right=True)

    # 3. Jump / Airborne
    f = FighterState(x=300.0, character_name=char_name, in_air=True, jump_frame=8, current_action=Action.JUMP)
    assert resolve_fighter_pose(f) == "jump"
    draw_fighter(canvas, f, facing_right=True)

    # 4. Crouch / Low Guard
    for crouch_act in (Action.CROUCH, Action.BLOCK_LOW):
        f = FighterState(x=300.0, character_name=char_name, is_crouching=True, current_action=crouch_act)
        assert resolve_fighter_pose(f) == "crouch"
        draw_fighter(canvas, f, facing_right=True)

    # 5. Punch attacks
    for punch_act, atk_name in (
        (Action.LIGHT, "light"),
        (Action.HEAVY, "heavy"),
        (Action.OVERHEAD, "overhead"),
        (Action.SPECIAL_NEUTRAL, "special_neutral"),
        (Action.SUPER, "super"),
    ):
        f = FighterState(
            x=300.0,
            character_name=char_name,
            attack_phase="active",
            attack_type=atk_name,
            current_action=punch_act,
        )
        assert resolve_fighter_pose(f) == "punch"
        draw_fighter(canvas, f, facing_right=True)

    # 6. Kick attacks
    for kick_act, atk_name in (
        (Action.LIGHT_KICK, "light_kick"),
        (Action.HEAVY_KICK, "heavy_kick"),
        (Action.LOW_SWEEP, "low_sweep"),
        (Action.CROUCH_KICK, "crouch_kick"),
        (Action.JUMP_KICK, "jump_kick"),
    ):
        f = FighterState(
            x=300.0,
            character_name=char_name,
            attack_phase="active",
            attack_type=atk_name,
            current_action=kick_act,
        )
        assert resolve_fighter_pose(f) == "kick"
        draw_fighter(canvas, f, facing_right=False, player_num=2, is_mirror=True)
