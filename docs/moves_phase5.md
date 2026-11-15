# Arena-AI Phase 5: AI with the Big Move Set

## 1. Overview

Phase 5 equips the 4 AI personalities with the complete moveset, macro-actions, minimax lookahead search with iterative deepening, and difficulty level scaling.

---

## 2. Personality Archetypes & Macro-Actions

1. **Crimson Brawler (Rushdown)**:
   - Uses armored *Berserker Charge* to close distance against pokes.
   - Confirms strings into *Crimson Rush* and *Rising Uppercut*.
   - Uses *Clinch Slam* command grab against turtling defenders.
   - Defensively bursts when caught in combos below 40% health.
   - Spends full meter or 60 Fury meter on *Blood Fury* super.

2. **Steel Guardian (Counter-Fighter)**:
   - Turtles behind standing and crouching block, looking for block punishes.
   - Triggers *Iron Wall* counter stance against telegraphed strikes.
   - Uses *Shield Bash* when cornered to reverse arena position.
   - Reflects projectiles with *Reflector*.
   - Breaks high guard with *Punisher Grip* command grab.

3. **Shadow Striker (Hit-and-Run / Zoner)**:
   - Zones from afar with *Energy Dart* projectiles.
   - Uses *Shadow Step* to swap sides and escape corner pressure.
   - Mixes up defenses with *Phantom Kick* (low startup).
   - Utilizes double jumps and air mobility to bait anti-airs.

4. **Golden Tactician (Adaptive)**:
   - Analyzes opponent move frequency with the online opponent model.
   - Deploys *Golden Read* when an opponent exhibits high attack repetition.
   - Punishes recovery frames with high-damage *Gambit Strike*.
   - Cycles stances to match the current fight distance.
   - Confirms into *Checkmate* super.

---

## 3. Lookahead Search & Real-Time Budget

- **Lookahead Search**: Implemented in [`backend/ai/search.py`](file:///c:/Users/Muhammad%20Abdul%20Wahid/PycharmProjects/AIProject/backend/ai/search.py) with 3 plies of minimax search and alpha-beta pruning over key branch actions (attacks, blocks, throws).
- **Iterative Deepening**: Explores depth 1, then depth 2, then depth 3.
- **Strict 5ms Time Budget**: Bounded strictly to under 5.0 milliseconds per frame, guaranteeing a rock-solid 60 FPS update rate during gameplay.

---

## 4. Difficulty Scaling

Configured in [`backend/ai/difficulty.py`](file:///c:/Users/Muhammad%20Abdul%20Wahid/PycharmProjects/AIProject/backend/ai/difficulty.py):
- **LOW**:
  - 20% optimal decision rate (80% mistake chance).
  - 24-frame reaction delay.
  - No cancels or complex strings.
- **MEDIUM**:
  - 50% optimal decision rate (50% mistake chance).
  - 15-frame reaction delay.
  - Confirms 2-hit strings and parries telegraphed attacks.
- **HIGH**:
  - 85% optimal decision rate (15% mistake chance).
  - 5-frame reaction delay.
  - Full combo confirms, optimal whiff punishes, defensive bursting, and 3-ply minimax lookahead.
