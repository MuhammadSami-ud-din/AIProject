# Shield Wall - Step 5: Verification, Balance Benchmark & Soak Test

## Verification Suite (`tests/test_shield_wall.py`)
All 15 unit tests pass, covering:
- Energy cost, regeneration, and turtle penalty.
- 6s cooldown and strict max-1 shield rule.
- 8f startup vulnerability (5f for Shadow).
- Every counterplay rule: throws ignore & remove shields, heavy attacks x2 (x2.5 Crimson) + 15% chip, overheads jump over, attack self-drain (-3 HP).
- 20-frame Shield Break stun.
- Physical wall movement collision (no fighter ever stuck inside a shield) and determinism.

## Balance Report & Soak Test (`backend/data/shield_balance.py`)
- Executed 200 matches per pair on `HIGH` difficulty with shields ON vs OFF (2,400 total matches) + 1,000-match randomized soak test.
- Results saved to `docs/results/shield_balance.md`.
