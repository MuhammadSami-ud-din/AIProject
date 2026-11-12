# Playable Game (M3)

## How to run
```
uv run python -m frontend
```

## Controls
| Key | Action |
|-----|--------|
| A / D | Move left / right |
| W | Jump |
| J | Light attack |
| K | Heavy attack |
| L | Block |
| Esc | Pause |
| ↑ / ↓ | Navigate menus |
| Enter | Confirm selection |

## Screens
1. **Intro**: Title screen — press any key.
2. **Main Menu**: Start Match, AI Model Fight, Settings, Statistics, Quit.
3. **Character Select**: Pick from Crimson, Steel, Shadow, Golden, or Random. Shows full name and description.
4. **Mode Select**: Pick match type (Human vs AI, Human vs Random, AI vs AI) then difficulty.
5. **Fight Screen**: Health bars, timer, round counter, hit flash. Fighters drawn as shapes with costume colours.
6. **Pause**: Esc to pause, resume or quit to menu.
7. **Results**: Shows who won the match.
8. **Settings**: Toggle fight logging on/off (off by default).

## Fighter rendering
Each fighter is drawn with pygame shapes only:
- Circle head, rectangle body, line arms and legs.
- Colours from `FIGHTER_COLOURS` dict in `colours.py`.
- Attack animation: arm extends during active phase, pulls back during startup.
- Block indicator: blue shield rectangle.
- Jump: sine-curve arc, 120px max height.

## Files
| File | Purpose |
|------|---------|
| `frontend/main.py` | Entry point, menu flow, agent creation |
| `frontend/screens.py` | All menu screens (intro, main, char select, mode, pause, results, settings, statistics) |
| `frontend/fight_screen.py` | The fight loop with rendering |
| `frontend/draw_fighter.py` | Shape-based fighter rendering |
| `frontend/hud.py` | Health bars, timer, round counter |
| `frontend/input_handler.py` | Keyboard → Action mapping |
| `frontend/colours.py` | All colours, sizes, and UI constants |
