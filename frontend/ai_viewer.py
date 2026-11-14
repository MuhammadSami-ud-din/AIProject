"""AI Model Fight Viewer: watch two AIs fight with full thinking display.

Shows each fighter's top move choices with confidence bars,
evaluation contributions, opponent model prediction indicator,
and a toggleable F3 profiling overlay. Speed is adjustable.
"""

import pygame
import sys

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.ai.choice import top_choices
from backend.ai.evaluation import evaluate
from backend.ai.explain import explain_action, commentary
from backend.engine.constants import ARENA_WIDTH, FPS
from backend.engine.step import make_initial_state, new_round, step
from frontend.colours import (
    BLACK,
    DARK_GREY,
    HEALTH_GREEN,
    LIGHT_GREY,
    MENU_BG,
    MENU_HIGHLIGHT,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TIMER_COLOUR,
    WHITE,
)
from frontend.draw_fighter import draw_fighter
from frontend.hud import draw_hud
from frontend.screens import pause_screen


# Layout constants
ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2
GROUND_Y = 350          # raised to make room for info panels below
PANEL_Y = 420            # where the info panels start
PANEL_HEIGHT = 170       # height of each info panel

# Speed settings: list of (label, fps_multiplier)
SPEED_OPTIONS = [
    ("0.25x", 0.25),
    ("0.5x", 0.5),
    ("1x", 1.0),
    ("2x", 2.0),
    ("4x", 4.0),
]
DEFAULT_SPEED_INDEX = 2  # start at 1x


def run_ai_viewer(surface, clock, agent1, agent2):
    """Run an AI-vs-AI match with full thinking display.

    agent1, agent2: the two AI agents.
    Returns the match result: "p1", "p2", or "draw".
    """
    # Figure out character names from the agents
    char1 = agent1.personality.name if agent1.personality else "Golden"
    char2 = agent2.personality.name if agent2.personality else "Golden"

    state = make_initial_state(char1, char2)
    agent1.reset()
    agent2.reset()

    # Fonts
    font_large = pygame.font.Font(None, 48)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)
    font_tiny = pygame.font.Font(None, 16)

    # State for the viewer
    speed_index = DEFAULT_SPEED_INDEX
    show_profiling = False       # toggled with F3
    paused = False

    # Last-frame info for display
    info1 = _empty_info()
    info2 = _empty_info()

    prev_health1 = 1.0
    prev_health2 = 1.0
    hit_flash = 0

    while not state.match_over:
        # --- Handle events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    result = pause_screen(surface, clock)
                    if result == "quit":
                        return "quit"
                # Speed controls: left/right arrows
                elif event.key == pygame.K_LEFT:
                    speed_index = max(0, speed_index - 1)
                elif event.key == pygame.K_RIGHT:
                    speed_index = min(len(SPEED_OPTIONS) - 1, speed_index + 1)
                # F3 toggles profiling overlay
                elif event.key == pygame.K_F3:
                    show_profiling = not show_profiling
                # Space pauses/unpauses
                elif event.key == pygame.K_SPACE:
                    paused = not paused

        # If paused, just draw and wait
        if paused:
            _draw_full_frame(
                surface, state, info1, info2,
                font_medium, font_small, font_tiny,
                hit_flash, speed_index, show_profiling, paused,
                agent1, agent2
            )
            pygame.display.flip()
            clock.tick(30)
            continue

        # --- Get actions and record thinking ---
        obs1 = observation_for(state, 1)
        obs2 = observation_for(state, 2)
        action1, scores1 = agent1.decide(obs1)
        action2, scores2 = agent2.decide(obs2)

        # Build info dicts for display
        info1 = _build_info(agent1, action1, scores1, obs1)
        info2 = _build_info(agent2, action2, scores2, obs2)

        # --- Step engine ---
        state = step(state, action1, action2)

        # --- Hit flash ---
        if state.fighter1.health < prev_health1 or state.fighter2.health < prev_health2:
            hit_flash = 4
        prev_health1 = state.fighter1.health
        prev_health2 = state.fighter2.health
        hit_flash = max(0, hit_flash - 1)

        # --- Let agents observe ---
        obs1 = observation_for(state, 1)
        obs2 = observation_for(state, 2)
        agent1.observe(obs1, action1, action2)
        agent2.observe(obs2, action2, action1)

        # --- Draw ---
        _draw_full_frame(
            surface, state, info1, info2,
            font_medium, font_small, font_tiny,
            hit_flash, speed_index, show_profiling, paused,
            agent1, agent2
        )
        pygame.display.flip()

        # --- Tick at the chosen speed ---
        _, speed_mult = SPEED_OPTIONS[speed_index]
        clock.tick(int(FPS * speed_mult))

        # --- Round transition ---
        if state.round_over and not state.match_over:
            _show_round_result(surface, state, font_large, clock)
            state = new_round(state)
            agent1.reset()
            agent2.reset()
            prev_health1 = 1.0
            prev_health2 = 1.0

    return state.match_result


# ------------------------------------------------------------------
# Info helpers
# ------------------------------------------------------------------
def _empty_info():
    """Default empty info dict before the first frame."""
    return {
        "action": Action.IDLE,
        "top_choices": [],
        "explanation": "",
        "commentary": "",
        "eval_score": 0.0,
        "contributions": {},
        "decision_ms": 0.0,
        "opp_model_accurate": False,
        "opp_model_prediction": None,
    }


def _build_info(agent, action, scores, obs):
    """Build the display info dict for one agent."""
    personality = agent.personality
    variety = personality.variety if personality else 0.0

    # Top choices with probabilities
    choices = []
    if scores:
        choices = top_choices(scores, variety, n=4)

    # Explanation text
    explanation = explain_action(action, obs, scores, personality)

    # Commentary text
    comment = commentary(obs, personality)

    # Evaluation score and contributions
    eval_score = 0.0
    contributions = {}
    if personality:
        eval_score, contributions = evaluate(obs, personality)

    # Opponent model prediction indicator
    opp_accurate = False
    opp_prediction = None
    # Check if the agent (or its inner agent) has an opponent model
    inner = getattr(agent, "inner", agent)
    model = getattr(inner, "opp_model", None)
    if model is not None:
        opp_accurate = model.is_confident
        if model.last_prediction is not None:
            opp_prediction = model.last_prediction.name

    return {
        "action": action,
        "top_choices": choices,
        "explanation": explanation,
        "commentary": comment,
        "eval_score": eval_score,
        "contributions": contributions,
        "decision_ms": agent.last_decision_ms,
        "opp_model_accurate": opp_accurate,
        "opp_model_prediction": opp_prediction,
    }

    # Evaluation score and contributions
    eval_score = 0.0
    contributions = {}
    if personality:
        eval_score, contributions = evaluate(obs, personality)

    return {
        "action": action,
        "top_choices": choices,
        "explanation": explanation,
        "commentary": comment,
        "eval_score": eval_score,
        "contributions": contributions,
        "decision_ms": agent.last_decision_ms,
    }


# ------------------------------------------------------------------
# Drawing
# ------------------------------------------------------------------
def _draw_full_frame(surface, state, info1, info2,
                     font_medium, font_small, font_tiny,
                     hit_flash, speed_index, show_profiling, paused,
                     agent1, agent2):
    """Draw one complete frame: arena + fighters + HUD + AI panels."""
    surface.fill(MENU_BG)

    # Arena floor
    floor_rect = pygame.Rect(ARENA_OFFSET_X, GROUND_Y, ARENA_WIDTH, 4)
    pygame.draw.rect(surface, DARK_GREY, floor_rect)

    # Arena walls
    pygame.draw.line(surface, DARK_GREY,
                     (ARENA_OFFSET_X, GROUND_Y - 200),
                     (ARENA_OFFSET_X, GROUND_Y + 4), 2)
    pygame.draw.line(surface, DARK_GREY,
                     (ARENA_OFFSET_X + ARENA_WIDTH, GROUND_Y - 200),
                     (ARENA_OFFSET_X + ARENA_WIDTH, GROUND_Y + 4), 2)

    # Fighters
    f1 = state.fighter1
    f2 = state.fighter2
    facing1 = f1.x < f2.x
    facing2 = f2.x < f1.x
    draw_fighter(surface, f1, facing1, ARENA_OFFSET_X, GROUND_Y)
    draw_fighter(surface, f2, facing2, ARENA_OFFSET_X, GROUND_Y)

    # HUD (health bars, timer, rounds)
    draw_hud(surface, state, font_medium, font_small, hit_flash)

    # Speed indicator at the top right
    speed_label, _ = SPEED_OPTIONS[speed_index]
    speed_text = font_small.render(f"Speed: {speed_label} (←/→)", True, TIMER_COLOUR)
    surface.blit(speed_text, (SCREEN_WIDTH - 180, 5))

    # Pause indicator
    if paused:
        pause_text = font_medium.render("PAUSED (Space)", True, WHITE)
        rect = pause_text.get_rect(center=(SCREEN_WIDTH // 2, GROUND_Y - 30))
        surface.blit(pause_text, rect)

    # --- AI thinking panels ---
    panel_width = SCREEN_WIDTH // 2 - 20
    _draw_ai_panel(surface, 10, PANEL_Y, panel_width, info1,
                   agent1.name, font_small, font_tiny, "left")
    _draw_ai_panel(surface, SCREEN_WIDTH // 2 + 10, PANEL_Y, panel_width, info2,
                   agent2.name, font_small, font_tiny, "right")

    # --- Profiling overlay (F3) ---
    if show_profiling:
        _draw_profiling(surface, agent1, agent2, font_tiny)


def _draw_ai_panel(surface, x, y, width, info, name, font_small, font_tiny, side):
    """Draw one AI's thinking panel: choices, explanation, evaluation."""
    # Panel background
    panel_rect = pygame.Rect(x, y, width, PANEL_HEIGHT)
    pygame.draw.rect(surface, (20, 20, 40), panel_rect, border_radius=5)
    pygame.draw.rect(surface, DARK_GREY, panel_rect, 1, border_radius=5)

    # Agent name
    label = font_small.render(name, True, WHITE)
    surface.blit(label, (x + 8, y + 4))

    # Current action
    action_name = info["action"].name
    action_text = font_tiny.render(f"Action: {action_name}", True, TIMER_COLOUR)
    surface.blit(action_text, (x + 8, y + 24))

    # Top choices with confidence bars
    bar_x = x + 8
    bar_y = y + 42
    bar_width = width // 2 - 20
    bar_height = 12

    for i, (action, prob) in enumerate(info["top_choices"][:4]):
        if bar_y + i * 18 > y + PANEL_HEIGHT - 10:
            break

        # Action name
        act_label = font_tiny.render(action.name, True, LIGHT_GREY)
        surface.blit(act_label, (bar_x, bar_y + i * 18))

        # Confidence bar
        bx = bar_x + 60
        by = bar_y + i * 18 + 2
        # Background
        pygame.draw.rect(surface, DARK_GREY, (bx, by, bar_width, bar_height))
        # Fill
        fill_w = int(bar_width * min(prob, 1.0))
        if fill_w > 0:
            colour = HEALTH_GREEN if prob > 0.5 else TIMER_COLOUR
            pygame.draw.rect(surface, colour, (bx, by, fill_w, bar_height))
        # Percentage text
        pct = font_tiny.render(f"{prob:.0%}", True, WHITE)
        surface.blit(pct, (bx + bar_width + 4, by - 1))

    # Explanation (right half of panel)
    text_x = x + width // 2 + 4
    text_y = y + 42

    # Explanation line (wrap if needed)
    explanation = info.get("explanation", "")
    _draw_wrapped_text(surface, explanation, font_tiny, LIGHT_GREY,
                       text_x, text_y, width // 2 - 12, 3)

    # Commentary line
    comment = info.get("commentary", "")
    comment_text = font_tiny.render(comment[:60], True, TIMER_COLOUR)
    surface.blit(comment_text, (text_x, text_y + 48))

    # Evaluation score
    score = info.get("eval_score", 0.0)
    score_text = font_tiny.render(f"Eval: {score:.1f}", True, WHITE)
    surface.blit(score_text, (text_x, text_y + 66))

    # Top 3 evaluation contributions
    contributions = info.get("contributions", {})
    if contributions:
        # Sort by absolute value, show top 3
        sorted_contribs = sorted(contributions.items(),
                                 key=lambda kv: abs(kv[1]), reverse=True)
        for i, (fname, val) in enumerate(sorted_contribs[:3]):
            colour = HEALTH_GREEN if val > 0 else (200, 80, 80)
            ct = font_tiny.render(f"{fname}: {val:+.1f}", True, colour)
            surface.blit(ct, (text_x, text_y + 84 + i * 14))

    # Decision time
    ms = info.get("decision_ms", 0.0)
    time_text = font_tiny.render(f"{ms:.1f}ms", True, LIGHT_GREY)
    surface.blit(time_text, (x + width - 50, y + 4))

    # Opponent model prediction indicator (green dot if accuracy > 70%)
    if info.get("opp_model_accurate"):
        pred = info.get("opp_model_prediction", "?")
        indicator_colour = HEALTH_GREEN
        pygame.draw.circle(surface, indicator_colour, (x + width - 60, y + 10), 5)
        pred_text = font_tiny.render(f"Pred:{pred}", True, indicator_colour)
        surface.blit(pred_text, (x + width - 130, y + 18))


def _draw_wrapped_text(surface, text, font, colour, x, y, max_width, max_lines):
    """Draw text wrapped to fit within max_width, up to max_lines."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = current_line + " " + word if current_line else word
        if font.size(test)[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
        if len(lines) >= max_lines:
            break
    if current_line and len(lines) < max_lines:
        lines.append(current_line)

    for i, line in enumerate(lines):
        rendered = font.render(line, True, colour)
        surface.blit(rendered, (x, y + i * 15))


def _draw_profiling(surface, agent1, agent2, font_tiny):
    """Draw the F3 profiling overlay showing timing data."""
    # Semi-transparent background
    overlay = pygame.Surface((280, 120), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surface.blit(overlay, (5, 100))

    y = 105
    x = 10
    header = font_tiny.render("F3 Profiling", True, TIMER_COLOUR)
    surface.blit(header, (x, y))
    y += 16

    for agent in [agent1, agent2]:
        name = agent.name
        ms = agent.last_decision_ms
        slowest = agent.slowest_decision_ms
        compliance = agent.budget_compliance

        line1 = f"{name}: {ms:.1f}ms (worst: {slowest:.1f}ms)"
        line2 = f"  Budget OK: {compliance:.0%}"
        surface.blit(font_tiny.render(line1, True, WHITE), (x, y))
        y += 14
        surface.blit(font_tiny.render(line2, True, LIGHT_GREY), (x, y))
        y += 14

        # Show breakdown if available
        if agent.last_breakdown:
            parts = [f"{k}:{v:.1f}" for k, v in agent.last_breakdown.items()]
            breakdown = "  " + ", ".join(parts)
            surface.blit(font_tiny.render(breakdown[:50], True, LIGHT_GREY), (x, y))
            y += 14


def _show_round_result(surface, state, font_large, clock):
    """Brief pause to show who won the round."""
    if state.round_result == "p1":
        text = f"{state.fighter1.character_name} wins the round!"
    elif state.round_result == "p2":
        text = f"{state.fighter2.character_name} wins the round!"
    else:
        text = "Round draw!"

    label = font_large.render(text, True, WHITE)
    rect = label.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))

    for _ in range(120):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        surface.fill(MENU_BG)
        surface.blit(label, rect)
        pygame.display.flip()
        clock.tick(FPS)
