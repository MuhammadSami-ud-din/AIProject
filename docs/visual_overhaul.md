# Visual Overhaul of the Fight Screen (Steps 1–6)

## Overview
All 6 steps of the Fight Screen Visual Overhaul have been implemented using pure code rendering (zero new image assets beyond existing backgrounds and portraits), preserving game rules, AI logic, and character balance while maintaining an average frame render time of **~4.6–5.0 ms/frame** (well under the 16.0 ms / 60 FPS budget).

---

## Step 1: Bug Fixes & Engine Polish
- **Pushboxes (`backend/engine/pushbox.py`, `backend/engine/step.py`)**:
  - Grounded fighters have per-character body collision half-widths (`Shadow: 14px`, `Golden: 15px`, `Crimson: 16px`, `Steel: 18px`).
  - Overlapping grounded fighters push apart evenly; when one fighter is pinned against an arena wall, the free fighter absorbs the remaining push.
  - Pushboxes only collide on the ground, so jumping over an opponent for cross-ups remains legal.
  - Verified by a 1,000-match seeded soak test in `tests/test_pushbox.py` with **0 grounded overlaps**.
- **Projectile Limits (`backend/engine/projectile_rules.py`)**:
  - Enforces a 150-frame (2.5 s) shot cooldown, max 1 active projectile per fighter on screen, and max 4 shots per fighter per round.
- **Debug Arena Box (`F2`)**:
  - The blue arena box is hidden during normal play and drawn only when debug/training view (`F2`) is active.
- **Viewport + `FLOOR_RATIO` System (`frontend/theme.py`, `F4`)**:
  - Added per-arena `FLOOR_RATIO` (`arena_frozen_peak: 0.85`, etc.) and `get_arena_floor_y()` so fighter feet stand directly on the floor artwork.
  - Pressing `F4` toggles red alignment guide lines showing `FLOOR_RATIO` and `floor_y`.
- **Aligned Action Explanations (`backend/ai/explain.py`)**:
  - Added dedicated templates for every `Action` in `ALL_ACTIONS` (`DASH` = *"dashes in"*, `BACKDASH` = *"backs off to make space"*, etc.); `"waiting"` is returned exclusively for `Action.IDLE`.
  - `_build_info()` in `frontend/ai_viewer.py` ensures the move badge, explanation sentence, and highlighted confidence bar always reflect the exact same decision.

---

## Step 2: Jointed Fighters & Keyframe Blending (`frontend/draw_fighter.py`)
- **Anatomical Jointed Limbs**:
  - Each fighter is rendered with a rounded head, torso, upper/lower arms, hands, upper/lower legs, and feet using capsule polygons with a 2-px dark outline (`OUTLINE_DARK`), directional shadow shading, and a light rim highlight.
- **Pose Keyframes & Blending**:
  - Keyframed poses for idle breathing, walking stride, dash lean, backdash, crouch, jump arc, light/heavy punches, kicks, block, hit reaction, and knockdown, smoothly interpolated over 3–4 frames (`alpha = 0.35`).
- **Unique Character Visual Signatures**:
  - **Crimson**: Spiked crimson hair, headband, sleeveless gi, white taped fists with red wraps, black belt with animated trailing ends, and rising flame wisps in Fury.
  - **Steel**: Heavy square shoulder pauldrons, glowing blue visor slit, mechanical elbow/knee joint rings, and forearm-mounted shield plate.
  - **Shadow**: Pointed cowl/hood, glowing teal eyes, multi-segment floating scarf, crisscross limb wraps, and dark mist dissolution on dash.
  - **Golden**: Open-chest martial artist robe, gold prayer beads necklace, flowing waist sash, and a rotating golden compass circle under his feet.
- **Ground Shadow & Dash Ghosts**:
  - Soft multi-layered oval ground shadow scales down and blurs as jump height increases.
  - 3 faded after-image silhouettes trail behind the fighter strictly during `DASH` and `BACKDASH`.

---

## Step 3: Effects, Impact & Arena Ambience (`frontend/camera_effects.py`, `frontend/hud.py`)
- **Starburst Hit Sparks**:
  - Clean hits spawn 8-point white/yellow polygon starbursts; blocked hits spawn blue-white hexagonal shield ripples; counter-hits spawn 10-point crimson starbursts with a brief screen flash.
- **Hit-Stop, Screen Shake & White Hurt Flash**:
  - Hit-stop freezes for 3f (light), 6f (heavy), and 10f (super), paired with scaled screen shake (`2 / 5 / 12 px`) and a 2-frame pure white hurt flash on the struck fighter.
- **Curved Motion Arcs & Dust Puffs**:
  - Smooth curved polygon slash arcs on punches and kicks; ground dust puffs on jump landing, dash start, and knockdown impact.
- **Floating Combat Text**:
  - `"COUNTER!"`, `"PUNISH!"`, and `"BLOCKED"` rise and fade over 20 frames with a 1-px dark outline.
- **Two-Layer Arena Ambience & Colour Grade**:
  - Atmospheric particles rendered both behind and in front of the fighters (falling snow on Frozen Peak, angled rain on Neon Rooftop, autumn leaves on Golden Temple, rising ember sparks on Volcanic Forge/Iron Foundry, glowing fireflies on Moonlit Bamboo, neon motes on Sky Colosseum), plus a cached colour-grade tint and soft edge vignette.

---

## Step 4: Dynamic Camera & KO Slow-Motion (`frontend/camera_effects.py`)
- Smoothly tracks the midpoint between the two fighters (`lerp_t = 0.10`) and zooms between `1.0x` (far) and `1.15x` (close), clamped to the arena boundaries.
- On a round-ending KO, triggers a 30-frame `0.3x` slow-motion sequence that zooms in on the defeated fighter before pulling back to `1.0x` for the `"K.O."` banner.
- Transforms only the fight viewport; the HUD and AI telemetry panel remain rock-steady.

---

## Step 5: Modern HUD Redesign (`frontend/hud.py`)
- **Slanted Parallelogram Health Bars**:
  - Gradient health fills: green (`> 60%`), yellow (`25–60%`), and pulsing red (`< 25%`) with a top highlight strip.
  - **15-Frame White Damage Drop**: Holds the pre-hit white bar for 15 frames before smoothly catching down to current HP.
- **Framed Portraits & Titles**:
  - Outer-edge character portraits in stylized borders, bold uppercase name + archetype subtitle above the bar, and glowing diamond round-win markers below.
- **Guard Meter, 3-Segment Super Meter & Hexagonal Timer**:
  - Slim slanted guard bar (cyan -> orange -> flashing red); 3-segment super bar with cyan fill and pulsing `"MAX"` energy ripple; centered hexagonal timer badge that turns red and pulses under 10 seconds.

---

## Step 6: Collapsible AI Telemetry Dashboard (`frontend/ai_viewer.py`)
- **Dark-Glass Telemetry Panel**:
  - Occupies the bottom 180 px (`80%` opacity dark blue-grey glass, rounded top corners, 1-px cyan top border) with zero overlap against the fight viewport above.
  - Pressing `Tab` toggles between `FULL` (180 px two-column dashboard) and `COLLAPSED` (slim 32 px status bar showing active move pill, confidence %, and latency).
- **Per-Fighter Telemetry Columns**:
  - Framed portrait, name, archetype, difficulty badge, color-coded active move pill (green=movement, red=attack, blue=defense, purple=special/super), and latency indicator (`ms / 60 FPS`) with green status dot.
  - Top 4 candidate actions with smooth `0.15s` easing bars, gold border, and selection arrow (`▶`) on the chosen move.
  - White explanation sentence, italic yellow tactical commentary, and a centered `-1.0..+1.0` win-probability bar with top 3 contributing factor chips.
