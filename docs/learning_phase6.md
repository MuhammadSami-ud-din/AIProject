# Phase 6: In-Game Model Deployment, Dynamic Difficulty Adjustment, & Model Insights

## Plain English Overview
In Phase 6, we bridge the offline neural network training pipeline directly into the live game engine and player interface:
1. **PolicyAgent (`backend/learning/policy_agent.py`)**:
   - An `Agent` subclass running PyTorch actor-critic policy inference entirely on CPU.
   - Masked sampling at temperature 1.0 (the distribution it was trained with) or `greedy=True` argmax; no personality temperature.
   - Same inputs as training: `policy_vector(obs)` and an action mask built from a FighterState reconstructed from all mask inputs in the Observation (thrown, throw-tech, guard-break stun, burst used, jump frame, attack phase).
   - Same granularity as training: one network query per macro-step, executed like `ArenaEnv.step`.
   - Model lookup: explicit path → registry "live" row → newest compatible `models/<char>/vNNN.pt` → `bc_model.pt`. Incompatible (e.g. old 30-feature) checkpoints are skipped with a log message.
   - Strict sub-millisecond execution budget timed cleanly with `with self.stage("policy"):`.
   - **Zero-Failure Fallback Guarantee**: If no trained model checkpoint exists on disk or in the registry, the agent seamlessly delegates to the rule-based FSM/search agent without throwing errors or freezing.
2. **Updated Difficulty Table & DDA (`backend/ai/difficulty.py`)**:
   - **LOW**: Rule-based FSM, high mistake rate, no model needed.
   - **MEDIUM**: Heuristic search, moderate mistake rate, no model needed.
   - **HIGH**: FSM + learned policy blend (weight 0.5), Bayesian opponent model.
   - **HELL**: FSM + learned policy blend (weight 0.7) + depth-1 simultaneous search (expectimax/minimax, 3 ms budget) + live opponent model.
   - All tiers: jittered human reaction time and occasional dropped/late inputs (see `docs/difficulty.md`).
   - **Dynamic Difficulty Adjustment (DDA)**: enabled with `adaptive_difficulty=True`; the game must call `wrapper.on_round_end(result)` after each round (and `on_match_end(result)` after a match). Over the last 5 rounds, if the human wins < 45% the AI's mistake chance rises by 5 points, if > 55% it falls. Damage, health and physics are never touched.
3. **Model Insights Screen (`frontend/screens.py`)**:
   - Accessible directly from the main menu under **Insights** or keyboard shortcut `I`.
   - Displays loaded model version for all 4 fighters (e.g. `v003 (Elo 1245)` or `Heuristic (no model)`).
   - Live telemetry: decision latency breakdown, top candidate actions with policy confidence percentages, predicted opponent action, and active personality reward bonuses.
   - Interactive **Background Training Manager**: pressing `T` spawns an isolated (`spawn`-context) `multiprocessing.Process` that runs BC → one PPO `train()` call → the real promotion gate, streaming progress through a non-blocking queue. `stop_training()` stops it cleanly. Checkpoints get new unique versions; the gate result reports the true win rate.

---

## What to Test by Hand
1. **Model Insights Screen**:
   - Launch the game: `uv run python -m frontend.main`
   - Select **Insights** from the main menu (or press `I`).
   - Confirm all 4 characters (Crimson, Steel, Shadow, Golden) are listed with their status (model version or heuristic fallback).
   - Check the top 3 candidate actions, confidence probabilities, and opponent prediction.
2. **Background Training Process**:
   - While on the Model Insights screen, press `T` (or click "Start Background Training").
   - Confirm that the progress bar activates, showing the current episode and rolling win rate.
   - Notice that the game UI remains completely smooth and responsive (no hitching or FPS drops) while training proceeds in the background process.
   - Press `T` again to safely stop the background training process.
3. **Fight with Policy Fallback**:
   - Start an AI vs AI or Player vs AI match on HIGH or HELL difficulty.
   - With checkpoints in `models/<char>/`, HIGH/HELL load them automatically; without (or if they fail to load), the FSM personality plays.
