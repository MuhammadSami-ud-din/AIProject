# Real-3D "2.5D" fight renderer

The fight scene is now rendered in real 3D with **moderngl**, offscreen, and
blitted into the normal pygame window. Menus, portraits, the HUD, popups and
banners are still drawn with pygame on top. Gameplay is still 2D. The engine's
`step(state, a1, a2)` is unchanged and remains the source of truth.

```
engine FightState ──push_step()──► FighterAnimator ×2 (pose: clips + procedural layers)
                                    │  FK + leg IK  ─►  bone matrices (rigid skinning)
render(state, frac, dt) ──► shadow map → MSAA HDR scene → resolve → bloom → composite
                            (tone map, gamma, grade, vignette, flip) → fbo.read → pygame.Surface
```

## Files (`frontend/render3d/`)

| file | what it does |
|---|---|
| `__init__.py` | `create_renderer()` and `gl_available()`. Returns `None` when OpenGL 3.3 is unavailable, so callers fall back to 2D. |
| `mathutil.py` | Matrices, eulers, quaternions and the look-at/projection helpers. 1 engine px is 0.01 m horizontally. |
| `meshes.py` | Procedural meshes with normals: sphere, tapered capsule, frustum, lathe, torus, rounded box and wedge. All are cached. |
| `skeleton.py` | A 20-bone hierarchy, per-character proportions, FK, analytic two-bone leg IK, a foot floor clamp and the smear stretch. |
| `characters.py` | The four code-built fighters. All parts of a fighter are baked into one VBO, so a whole fighter is one draw call. |
| `clips.py` | Stances, reaction poses and keyframed clips for **every move in `moves.py`** (plus burst, build, pickup and shield). |
| `animation.py` | Easing, clip sampling against real frame data, crossfades, procedural layers and verlet cloth chains. |
| `vfx.py` | Numpy-simulated billboard particles (sparks, rings, flashes, dust, aura, ambient) and ribbon trails. |
| `camera.py` | Midpoint tracking, distance zoom, directional shake, dutch tilt, push-in, super focus, KO orbit and the intro sweep. |
| `arena.py` | Per-arena light rig, procedural floor material, backdrop painting, props and ambient particles. |
| `renderer.py` | `Renderer3D` owns the GL context, framebuffers and passes, detects events and handles Rumble and Shield Wall objects. |
| `shaders.py` | GLSL 330 shaders: toon-ramp lighting with rim/fill/hemi, PCF shadows, floor, backdrop, particles and post. |

## Animation

* **Clips are driven by the engine.** `move_time()` converts `attack_phase` and
  `attack_frames_left` into a clip time, using the move's real startup, active
  and recovery numbers. Keys are tagged `("s"|"a"|"r", fraction)`. The strike
  key is `("a", 0)`, so full extension lands exactly on the first active frame.
  The pose holds through active, then follow-through and an overshoot-settle
  play out during recovery. `tests/test_render3d.py` checks this alignment for
  every move of every character.
* **Easing:** anticipation uses ease-in-out, the strike is a fast whip into a
  hard stop ("snap"), and recovery uses `back` (overshoot). The striking limb
  is stretched (*smear*) on contact.
* **Layers:** a guard stance per character, then a crouch, block and dash
  weight (smoothed), then a walk/run cycle with foot planting. The cycle phase
  advances by the distance actually moved, and IK pins planted feet. On top of
  that come breathing or a boxer bounce, landing squash, an additive hit-recoil
  spring, and a hitstop shake.
* **States:** jump (take-off, tuck, fall, Shadow's double-jump flip), hit
  reactions (high head snap / mid body fold / low buckle, scaled by
  strength), juggle tumble, knockdown (fall, bounce, lie, get-up), KO,
  thrown, guard-break stagger, parry deflect, burst, victory and defeat
  (kneel), and the super cinematic pose.
* **Crossfades:** 1–3 frames into attacks (never later than the active frame),
  2 into hits, and 6 for locomotion.
* **Cloth:** Shadow's scarf, Golden's sash tails and Crimson's headband tails
  are verlet chains rendered as extra bones.

## Fighters

* **Golden:** an old master in a white robe. Grey topknot and beard, a gold
  lapel and compass emblem, ornate gold bracers, a gold sash with trailing
  tails, and wide robe trousers. He uses an open-palm tactician stance.
* **Crimson:** a broad-shouldered brawler. Red sleeveless gi with black
  lapels, a flame emblem, bare muscular arms, red hand wraps, spiky black hair
  and a red headband with flowing tails. He uses a bouncing boxer guard.
* **Shadow:** a slim hooded ninja. Purple hood and outfit, a black mask,
  glowing teal eyes, black arm wraps, knee pads and a long trailing scarf. She
  uses a low wide stance.
* **Steel:** a bulky armoured guardian. Layered pauldrons, a breastplate, a
  great helm with a glowing blue visor and crest, a navy tabard, and glowing
  kite shields on both forearms.

## Integration (`frontend/fight_screen.py`)

* `run_fight(..., renderer=None, settings=None)` is backward compatible.
  * The renderer is chosen by `renderer=` or `settings["renderer"]` (`"3d"` by
    default, or `"2d"`).
  * The environment variable `FIGHT_RENDERER=2d` forces 2D.
  * If GL context creation fails (or fails mid-match), the legacy
    `draw_fighter` sprite path is used automatically.
* There is a **fixed-timestep accumulator**: 60 sim steps/s × game speed,
  rendered at display rate, with at most 4 steps per frame. Hitstop freezes the
  sim but rendering continues, and the struck fighter shakes. A non-sleeping
  clock (as used in the tests) gives 1 step per frame.
* **Local versus:** `human_player="both"` creates two
  `InputHandler(player=1|2)`, and `SUPPORTS_LOCAL_VERSUS = True` is set.
* **Audio hooks:** `play_swing`, `play_hit`, `play_block`, `play_parry`,
  `play_ko`, `play_special`, `play_super`, `play_throw`, `play_jump`,
  `play_land` and `play_dash` are called with stereo pan. They are
  getattr-guarded and fall back to the old `play_sfx` names.
* `r3d.push_step(prev, state)` runs after every engine step, *before*
  one-frame `last_hit_effect` values are consumed. "hit" and "block" no longer
  create popups.
* In 3D mode, popup positions are projected from 3D. The round intro has a
  camera sweep. KO slow motion uses a 3D orbit and keeps animating at 0.3×.

## Performance (M1, 1024×600, MSAA 4×, 2048² shadow map, bloom, planar reflections)

Mean frame cost is **8.6 ms** (p50 8.1 ms, p95 12.3 ms). That covers
animation, CPU particles, GPU work and readback, measured over 840 frames of a
scripted fight with `scratchpad/perf.py`. The rest of the 16.7 ms budget is
left for the engine, AI and HUD. Each fighter is drawn as one call per pass.

## Screenshots

These are in `docs/results/render3d/`:

* **Idle stances:** `idle_*.png`
* **Moves:** `jab_active_Crimson`, `heavy_kick_active_Golden`, `sweep_Shadow`,
  `uppercut_Crimson`, `block_Steel`, `hit_reaction_Golden`, `knockdown_Steel`
* **Specials and supers:** `special_*`, `super_freeze_Golden`, `super_hit_Steel`
* **Sheets:** `sequence_heavy_kick_Golden` (8 frames across the move),
  `sequence_heavy_punch_Crimson`, `arenas`, `contact_moves`

## Known limitations

* Faces are simple. Hands are fists (no fingers).
* Cloth chains don't collide with the body.
* Fighters can overlap visually at point-blank range, because the engine
  pushbox is only about 30 px.
* Rumble and Shield Wall objects are simple glowing boxes and panels.
* The backdrop is a painted panorama, so it has no true parallax inside the
  image.
