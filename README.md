# AIProject
A 2.5D fighting game featuring a reinforcement-learning-based combat AI, built as an Artificial Intelligence course project.

Fights are rendered in real-time 3D (moderngl) on a 2D gameplay plane; menus and HUD use pygame-ce.
If OpenGL is unavailable the game falls back to the classic 2D sprite renderer
(also selectable in Settings → Fight Graphics, or with `FIGHT_RENDERER=2d`).

## Run

```bash
uv sync                      # first time: install dependencies (Python 3.14+)
uv run python -m frontend    # launch the game
```

Controls: P1 `A/D` move, `W` jump, `S` crouch, `J K U I` attacks, `L` block, `O` special, `P` super.
P2 (Local Versus) uses arrows + numpad. Gamepads are supported. Rebind keys in Settings → Controls.

## Tests

```bash
uv run pytest
```

## Training the AI

```bash
uv run python -m backend.learning.bc     --character crimson --matches 24 --epochs 12
uv run python -m backend.learning.ppo    --character crimson --updates 80 --n-envs 4 --steps-per-env 128
uv run python -m backend.learning.league --character crimson --matches 24
uv run python -m backend.learning.eval   ablation --character crimson
```

See `docs/manual.md` (game rules), `docs/render3d.md` (3D renderer) and `docs/learning*.md` (AI).
