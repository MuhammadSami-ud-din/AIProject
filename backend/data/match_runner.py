"""Run a complete match between two AI agents with no graphics.

This is the core loop: step the engine, ask each agent for an action,
feed them the observation, repeat until the match ends.
Returns a list of frame records for logging.
"""

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.engine.step import make_initial_state, new_round, step


def run_match(agent1, agent2, seed=None, character1="Golden", character2="Golden",
              rules=None, record_frames=True):
    """Run a full match (up to 3 rounds) between two agents.

    Returns a dictionary with:
      - "frames": list of frame records (one dict per frame)
      - "match_result": "p1", "p2", or "draw"
      - "seed": the seed used
      - "rounds": list of round results
    """
    # Use the agents' character names if available from personality
    if agent1.personality:
        character1 = agent1.personality.name
    if agent2.personality:
        character2 = agent2.personality.name

    match_seed = seed if seed is not None else 42
    state = make_initial_state(character1, character2, rules=rules, seed=match_seed)
    frames = []
    rounds = []
    round_num = 1

    # Reset both agents for the first round
    agent1.reset()
    agent2.reset()

    while not state.match_over:
        # Build observations for each agent
        obs1 = observation_for(state, 1)
        obs2 = observation_for(state, 2)

        # Ask each agent what to do
        action1, _ = agent1.decide(obs1)
        action2, _ = agent2.decide(obs2)

        # Step the engine forward one frame
        new_state = step(state, action1, action2)

        # Record this frame if requested
        if record_frames:
            record = _make_frame_record(
                state=state,
                obs1=obs1,
                action1=action1,
                action2=action2,
                agent1=agent1,
                agent2=agent2,
                seed=seed,
                round_num=round_num,
            )
            frames.append(record)

        # Let agents observe what happened
        agent1.observe(obs1, action1, action2)
        agent2.observe(obs2, action2, action1)

        state = new_state

        # If the round ended, prepare for the next one
        if state.round_over:
            rounds.append(state.round_result)

            if not state.match_over:
                round_num += 1
                state = new_round(state)
                agent1.reset()
                agent2.reset()

    return {
        "frames": frames,
        "match_result": state.match_result,
        "seed": seed,
        "rounds": rounds,
        "p1_rounds_won": state.p1_rounds_won,
        "p2_rounds_won": state.p2_rounds_won,
    }


def _make_frame_record(state, obs1, action1, action2, agent1, agent2,
                        seed, round_num):
    """Build one row of data for the frame log."""
    # Get the feature numbers from player 1's observation
    features = obs1.features()

    record = {
        "frame": state.frame,
        "round": round_num,
        "agent1_name": agent1.name,
        "agent1_difficulty": agent1.difficulty,
        "agent2_name": agent2.name,
        "agent2_difficulty": agent2.difficulty,
        "seed": seed,
        "action1": action1.name,
        "action2": action2.name,
    }

    # Add all feature columns
    for name, value in features.items():
        record[name] = value

    return record
