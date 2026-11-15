# Arena-AI Phase 4: Signature Moves, Projectiles & Particles

## 1. Overview

Phase 4 gives each of the 4 fighters their full signature moveset, projectiles, armored attacks, command grabs, and supers. All names and properties are 100% original.

Move data is centralized in [`backend/engine/moves.py`](file:///c:/Users/Muhammad%20Abdul%20Wahid/PycharmProjects/AIProject/backend/engine/moves.py).

---

## 2. Character Signature Moves

### Crimson Brawler (Rushdown Archetype)
- **Crimson Rush** (`Forward + O`): Fast 3-hit dashing punch string (12 HP). Automatically chains on hit.
- **Rising Uppercut** (`O` / Neutral Special): Invincible startup anti-air launcher (11 HP) that pops opponents up for juggles.
- **Berserker Charge** (`Back + O`): Armored forward charge (9 HP). Absorbs 1 incoming hit at 50% damage without flinching.
- **Clinch Slam** (`Down + O`): Command grab (14 HP). Completely ignores blocking and ground-bounces the opponent.
- **Super: Blood Fury** (`P`): 8-hit barrage finisher (32 HP). Costs 100 meter (60 in Fury).

### Steel Guardian (Counter-Fighter Archetype)
- **Iron Wall** (`Down + O`): Counter stance (active 24f). If struck during stance, negates damage and retaliates with a heavy 16 HP counter-strike.
- **Shield Bash** (`Forward + O`): Heavy shield attack (8 HP, costs 25 meter). Blows the opponent 95 pixels across the arena to escape the corner.
- **Punisher Grip** (`O` / Neutral Special): Slow command grab (16 HP, 14f startup). Beats blocking opponents cleanly.
- **Reflector** (`Back + O`): Energy shield (active 20f). Reflects incoming projectiles back at their owner.
- **Super: Fortress Crush** (`P`): Counter super stance (active 30f). Triggers a massive 35 HP counter if hit during stance.

### Shadow Striker (Hit-and-Run / Zoner Archetype)
- **Shadow Step** (`Forward + O`): Teleport dash. Teleports directly behind the opponent with 6 frames of invulnerability.
- **Phantom Kick** (`Down + O`): Fast low-mid-mid kicking string (11 HP) that hits low on the opening frame.
- **Feint Strike** (`Back + O`): Deceptive attack wind-up that can cancel into throws or backdashes.
- **Energy Dart** (`O` / Neutral Special): Fast linear energy projectile (6 HP, 12 px/frame) fired across the arena.
- **Super: Vanishing Arts** (`P`): Teleport combo super (28 HP). Teleports through the opponent from all angles.
- **Passives**: Double jump (press jump in air) and horizontal air dash.

### Golden Tactician (Adaptive Archetype)
- **Tactician Stance** (`Down + O`): Stance cycle between Rush, Guard, and Evade stances.
- **Golden Read** (`O` / Neutral Special): Names a predicted opponent action based on the opponent model. If the opponent performs it within 30 frames, executes an instant 18 HP counter.
- **Gambit Strike** (`Forward + O`): High-risk high-reward poke (14 HP, -10 on block, massive hitstun on hit).
- **Tactical Step** (`Back + O`): Evasive backdash with 4 frames of invulnerability.
- **Super: Checkmate** (`P`): Unblockable cinematic super finisher (30 HP).

---

## 3. Deterministic Projectiles & Particles

- **Projectiles**: Tracked deterministically in `FightState.projectiles` (`x, y, vx, owner, lifetime, damage, hit_level`). Collisions and reflection follow pure mathematical checks.
- **Procedural Particles**: Rendered entirely through procedural Pygame primitives (circles, multi-ray sparkle lines, polygons) without external raster sprites or images.
