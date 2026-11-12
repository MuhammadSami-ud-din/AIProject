import pytest

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.random_agent import RandomAgent


def test_returns_valid_action_and_scores():
    action, scores = RandomAgent(seed=1).choose_action(None)
    assert action in ALL_ACTIONS
    assert set(scores) == set(ALL_ACTIONS)
    assert sum(scores.values()) == pytest.approx(1.0)


def test_same_seed_gives_same_moves():
    a, b = RandomAgent(seed=42), RandomAgent(seed=42)
    assert [a.choose_action(None)[0] for _ in range(200)] == [b.choose_action(None)[0] for _ in range(200)]


def test_uses_every_move_eventually():
    agent = RandomAgent(seed=0)
    assert {agent.choose_action(None)[0] for _ in range(1000)} == set(ALL_ACTIONS)


def test_holds_each_move_for_a_few_frames():
    agent = RandomAgent(seed=3, min_hold=4, max_hold=12)
    moves = [agent.choose_action(None)[0] for _ in range(600)]
    runs, count = [], 1
    for prev, cur in zip(moves, moves[1:]):
        if cur == prev:
            count += 1
        else:
            runs.append(count)
            count = 1
    assert min(runs) >= 4


def test_zero_weight_move_is_never_picked():
    agent = RandomAgent(seed=5, weights={Action.LIGHT: 3, Action.FORWARD: 1})
    moves = {agent.choose_action(None)[0] for _ in range(1000)}
    assert moves == {Action.LIGHT, Action.FORWARD}


def test_all_zero_weights_is_an_error():
    with pytest.raises(ValueError):
        RandomAgent(weights={})


def test_reset_starts_a_fresh_move():
    agent = RandomAgent(seed=1)
    agent.choose_action(None)
    agent.reset()
    assert agent.frames_left == 0 and agent.current_action is None


def test_base_agent_is_a_template():
    with pytest.raises(NotImplementedError):
        Agent().choose_action(None)


def test_agent_prints_nicely():
    assert str(RandomAgent(player=2)) == "Random (LOW, player 2)"


@pytest.mark.parametrize("bad_settings", [
    dict(min_hold=10, max_hold=2),
    dict(min_hold=0, max_hold=0),
    dict(weights={Action.LIGHT: 5, Action.BLOCK: -3}),
])
def test_bad_settings_are_rejected(bad_settings):
    with pytest.raises(ValueError):
        RandomAgent(**bad_settings)


def test_text_instead_of_move_is_rejected():
    with pytest.raises(TypeError):
        RandomAgent(weights={"LIGHT": 5})


@pytest.mark.parametrize("bad_settings", [
    {"player": 3},
    {"difficulty": "Hell"},
])
def test_base_agent_rejects_typos(bad_settings):
    with pytest.raises(ValueError):
        Agent(**bad_settings)


def test_personality_must_be_a_card_not_text():
    with pytest.raises(TypeError):
        Agent(personality="Crimson")


def test_agent_accepts_a_real_personality():
    from backend.ai.personalities import CRIMSON
    agent = Agent(name="Crimson", personality=CRIMSON, difficulty="HELL")
    assert agent.personality.closeness == 9


def test_reset_clears_last_scores():
    agent = RandomAgent(seed=1)
    agent.choose_action(None)
    agent.reset()
    assert agent.last_scores == {}


def test_move_lists_cannot_be_changed_by_accident():
    from backend.ai.actions import ATTACKS
    assert isinstance(ALL_ACTIONS, tuple)
    assert isinstance(ATTACKS, tuple)


# --- decide(): timing and safe fallback ------------------------------
class BrokenAgent(Agent):
    def choose_action(self, state):
        raise RuntimeError("bug in the brain")


class WrongAnswerAgent(Agent):
    def choose_action(self, state):
        return "LIGHT", {}


def test_decide_returns_the_move_and_measures_time():
    agent = RandomAgent(seed=1)
    action, scores = agent.decide(None)
    assert action in ALL_ACTIONS
    assert agent.last_decision_ms >= 0
    assert agent.slowest_decision_ms >= agent.last_decision_ms
    assert agent.within_frame_budget


def test_strict_mode_shows_the_bug():
    with pytest.raises(RuntimeError):
        BrokenAgent().decide(None)


def test_demo_mode_blocks_instead_of_crashing():
    agent = BrokenAgent()
    agent.strict = False
    action, _ = agent.decide(None)
    assert action == Action.BLOCK
    assert agent.fallback_count == 1


def test_returning_text_instead_of_a_move_is_caught():
    with pytest.raises(TypeError):
        WrongAnswerAgent().decide(None)


# --- Profiling: budget history and stage timing ---------------------------
class StagedAgent(Agent):
    def choose_action(self, state):
        with self.stage("thinking"):
            pass
        with self.stage("choosing"):
            pass
        return Action.IDLE, {Action.IDLE: 1.0}


def test_stage_timing_breakdown():
    agent = StagedAgent()
    agent.decide(None)
    assert set(agent.last_breakdown) == {"thinking", "choosing"}
    assert all(ms >= 0 for ms in agent.last_breakdown.values())


def test_decision_history_for_charts():
    agent = RandomAgent(seed=1)
    for _ in range(50):
        agent.decide(None)
    assert len(agent.decision_times) == 50
    assert agent.budget_compliance == 1.0
    assert agent.over_budget_count == 0


def test_history_keeps_only_recent_decisions():
    from backend.ai.base_agent import HISTORY_FRAMES
    agent = RandomAgent(seed=1)
    for _ in range(HISTORY_FRAMES + 100):
        agent.decide(None)
    assert len(agent.decision_times) == HISTORY_FRAMES


class SlowAgent(Agent):
    def choose_action(self, state):
        import time
        time.sleep(0.02)   # 20 ms: longer than one frame
        return Action.IDLE, {Action.IDLE: 1.0}


def test_slow_decisions_are_counted():
    agent = SlowAgent()
    agent.decide(None)
    assert agent.over_budget_count == 1
    assert agent.budget_compliance == 0.0
    assert not agent.within_frame_budget
