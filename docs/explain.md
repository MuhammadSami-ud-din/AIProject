# AI Explanation & Viewer — M7

## Explanation (`backend/ai/explain.py`)

Generates plain-English explanations for AI decisions.

### `explain_action(action, obs, scores, personality)`
Returns a one-sentence reason for the chosen action, like:
- "Steel blocked because the enemy just attacked."
- "Crimson rushed forward because the enemy is far away."

### `commentary(obs, personality)`
Returns a short commentary about the fight situation, like:
- "Crimson is cornered and low on health!"
- "Shadow has a big health lead."

## AI Model Fight Viewer (`frontend/ai_viewer.py`)

A special fight screen for watching two AIs play with full
thinking display:

### Controls
| Key | Action |
|-----|--------|
| ← / → | Change speed (0.25x to 4x) |
| Space | Pause / unpause |
| F3 | Toggle profiling overlay |
| Esc | Pause menu |

### What it shows
- **Top choices:** Each fighter's top 4 actions with confidence bars
- **Explanation:** One-sentence reason for the chosen action
- **Commentary:** Fight situation summary
- **Evaluation:** Score and top contributing factors
- **Decision time:** How long each decision took (in ms)

### F3 Profiling Overlay
Shows for each agent:
- Current decision time
- Worst decision time
- Budget compliance (% of decisions under 16.7ms)
- Timing breakdown by stage (search, scoring, etc.)
