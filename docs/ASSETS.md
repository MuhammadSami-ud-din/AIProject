# Asset Inventory & Provenance

This document lists every visual asset in Arena-AI, its role in the interface, and its provenance.

All assets are located in `frontend/assets/`. The game supports `.png`, `.jpg`, and `.jpeg`.
The asset manager (`frontend/assets.py`) guarantees safe loading:
1. Every asset is loaded and scaled to display dimensions **once** at startup.
2. If any asset is missing or corrupted, a graceful gradient placeholder with the asset name is displayed.
3. The game **never crashes** due to missing asset files.

---

## 1. Screen Art (`frontend/assets/screens/`)

| File Name | Role | Dimensions | Description / Theme |
| :--- | :--- | :--- | :--- |
| `intro.jpeg` | Intro Screen Key Art | 1024x600 (scaled) | Full illustration of Crimson Brawler and glowing "Arena-AI" title |
| `intro_blur.jpeg` | Menu Background | 1024x600 (scaled) | Soft Gaussian-blurred variant of the intro screen for legibility |
| `victory.jpeg` | Match Victory Screen | 1024x600 (scaled) | Golden radiant burst of light with celebration particles |
| `defeat.jpeg` | Match Defeat Screen | 1024x600 (scaled) | Dark rainy cobblestone ground under a stormy twilight sky |

*(Note: For match draws, `victory.jpeg` is dimmed dynamically by 55% in code).*

---

## 2. Fighter Portraits (`frontend/assets/portraits/`)

| File Name | Fighter | Role | Description / Key Motifs |
| :--- | :--- | :--- | :--- |
| `crimson.jpeg` | Crimson Brawler | Character Select / Results | Red martial gi, taped knuckles, flame emblem, determined expression |
| `steel.jpeg` | Steel Guardian | Character Select / Results | Heavy steel plate armor, shield crest, glowing visor, forearm shields |
| `shadow.jpeg` | Shadow Striker | Character Select / Results | Dark purple cowl, trailing scarf, glowing cyan eyes, crescent moon crest |
| `golden.jpeg` | Golden Tactician | Character Select / Results | Elegant white and gold robes, sash, compass emblem, veteran martial artist |

*(Note: In Character Select and results panels, Player 2's portrait is automatically mirrored horizontally).*

---

## 3. Arenas & Backgrounds (`frontend/assets/backgrounds/`)

The floor level for all arenas is set to the bottom 18% (`FLOOR_HEIGHT` = 492px on a 600px tall window).
A 25% dark overlay is automatically composited over arenas during combat to keep fighters clearly legible.

### Normal Arenas (Selected with match seed, non-repeating):
1. **`arena_neon_rooftop.jpeg`**: Cyberpunk high-rise rooftop in the rain, purple neon glow, distant skyscrapers.
2. **`arena_volcanic_forge.jpeg`**: Subterranean magma caverns, molten rock waterfall, anvils and iron chains.
3. **`arena_iron_foundry.jpeg`**: Industrial machinery hall, giant gears, exposed pipes and atmospheric steam.
4. **`arena_moonlit_bamboo.jpeg`**: Nighttime bamboo forest, wooden platform floor, full moon and fireflies.
5. **`arena_golden_temple.jpeg`**: Mountain shrine overlook at sunset, stone balustrades, stone lanterns and pagoda towers.
6. **`arena_frozen_peak.jpeg`**: Alpine mountain summit, stone hermitage, colorful prayer flags and snowy peaks.

### Special Arena:
7. **`arena_sky_colosseum.jpeg`**: Ancient floating marble ruins, mystical glowing runes, aurora borealis.
   - Used for all **HELL** difficulty showdowns.
   - Excluded from the random arena rotation pool.

---

## 4. Audio (CC0 Sound Fallback)

Optional sound effects (hit, block, KO, round intro) may be placed in `frontend/assets/sounds/`.
If no sound files are present, audio playback is safely bypassed with zero runtime overhead or warnings.
Audio mute is configurable in Settings.
