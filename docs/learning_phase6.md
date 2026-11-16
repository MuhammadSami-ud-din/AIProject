# Phase 6: In-Game Model Deployment, Dynamic Difficulty Adjustment, & Model Insights

## Plain English Overview
In Phase 6, we bridge the offline neural network training pipeline directly into the live game engine and player interface:
1. **PolicyAgent (`backend/learning/policy_agent.py`)**:
   - An `Agent` subclass running PyTorch actor-critic policy inference entirely on CPU.
   - Utilizes **masked softmax sampling** (rather than rigid argmax), scaled by the character's personality `variety` temperature. This prevents human players from trapping the AI in repetitive loops.
   - Strict sub-millisecond execution budget timed cleanly with `with self.stage("policy"):`.
   - **Zero-Failure Fallback Guarantee**: If no trained model checkpoint exists on disk or in the registry, the agent seamlessly delegates to the rule-based FSM/search agent without throwing errors or freezing.
2. **Updated Difficulty Table & DDA (`backend/ai/difficulty.py`)**:
   - **LOW**: Rule-based FSM, high mistake rate, no model needed.
   - **MEDIUM**: Heuristic search, moderate mistake rate, no model needed.
   - **HIGH**: Search blended with trained neural policy guidance, zero execution noise.
   - **HELL**: Deep search + policy guidance + dynamic opponent prediction.
   - **Dynamic Difficulty Adjustment (DDA)**: Tracks human win/loss streaks across rounds. If a player loses 3 rounds in a row, AI mistake chance increases slightly to prevent frustration. If the player wins 3 in a row, AI mistake chance decreases to sharpen the challenge. Damage, health, and physics are never touched—only decision error rates shift.
3. **Model Insights Screen (`frontend/screens.py`)**:
   - Accessible directly from the main menu under **Insights** or keyboard shortcut `I`.
   - Displays loaded model version for all 4 fighters (e.g. `v003 (Elo 1245)` or `Heuristic (no model)`).
   - Live telemetry: decision latency breakdown, top candidate actions with policy confidence percentages, predicted opponent action, and active personality reward bonuses.
   - Interactive **Background Training Manager**: pressing `T` / clicking "Start Background Training" spawns an isolated `multiprocessing.Process`. It streams live metrics (episodes, Elo, win rate against baseline) back to the screen via a non-blocking queue without ever stalling the Pygame 60 FPS main loop.

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
   - Even without pre-trained checkpoints, the game launches instantly and the fighters perform their character-specific moves and strategies seamlessly.
