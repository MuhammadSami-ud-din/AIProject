"""Campaign and Story mode definitions for Arena-AI.

Contains:
- 8 escalating tournament battles with dark-fantasy arena tournament lore.
- Character-specific story text formatting with player character interpolation.
- Intro dialogue quotes, epilogues, arenas, difficulty tiers, and level scaling offsets.
"""

from typing import Any, Dict, List

CAMPAIGN_BATTLES: List[Dict[str, Any]] = [
    {
        "id": 1,
        "title": "The Bloodgate Proving",
        "opponent": "Crimson",
        "arena": "Underground Vault",
        "difficulty": "LOW",
        "level_offset": 0,
        "reward_coins": 60,
        "story_paragraphs": [
            "The iron gates of the Sunken Arena groan open beneath the basalt spires. Challengers from across the realm have gathered to answer the call of the Sovereign Tournament.",
            "Standing in the blood-stained sand is Crimson, the berserker executioner. His jagged blades twitch with manic hunger, smelling the arrival of {warrior}.",
            "To advance deeper into the citadel, {warrior} must survive the opening onslaught and prove that steel and resolve triumph over reckless savagery."
        ],
        "intro_quote": "Another lamb walks to the slaughter! Let's see your guts spill across the flagstones!",
        "challenger_line": "Step aside, executioner. The Bloodgate opens for me today.",
        "challenger_reply": "Talk is cheap. Come test your fury against my fists!",
        "victory_epilogue": "Crimson collapses against the rusted iron bars, his blades trembling in the dust. The gate to the inner ring grinds open.",
    },
    {
        "id": 2,
        "title": "The Obsidian Bastion",
        "opponent": "Steel",
        "arena": "Temple Ruins",
        "difficulty": "LOW",
        "level_offset": 1,
        "reward_coins": 80,
        "story_paragraphs": [
            "Beyond the bloodgate lies the ancient courtyard of the Temple Ruins. The air grows cold and still as footsteps echo against weathered stone columns.",
            "A monolithic colossus clad in ancient runic armor steps forward. Steel, the Iron Bulwark, has never yielded an inch to any living contender.",
            "Direct force alone will not shatter this rampart. {warrior} must find the seam in his defense and outmaneuver the immovable wall."
        ],
        "intro_quote": "None breach the inner ring. Break upon my shield, contender.",
        "challenger_line": "An armored giant blocking the courtyard? Every wall has a crack, Steel!",
        "challenger_reply": "Keep your shield up—let's see how much impact that runic iron can take!",
        "victory_epilogue": "The colossus drops heavily onto one knee, cracks glowing along his runic plating. The path to the spires is cleared.",
    },
    {
        "id": 3,
        "title": "Whispers in the Gloom",
        "opponent": "Shadow",
        "arena": "Neon Rooftop",
        "difficulty": "MEDIUM",
        "level_offset": 2,
        "reward_coins": 100,
        "story_paragraphs": [
            "Ascending toward the Citadel's high terrace, rain slants through violet luminescent fog. The shadows themselves seem to detach from the rooftop parapets.",
            "From the dark haze emerges Shadow, the lethal vanguard assassin. Silent as mist and swift as a viper strike, he has snuffed out dozens of champions before they ever saw his blade.",
            "{warrior} must rely on razor reflexes and tight spacing, anticipating attacks that strike from blind angles in the dead of night."
        ],
        "intro_quote": "You cannot strike what you cannot see. Fall into darkness.",
        "challenger_line": "Come out of the mist, assassin. Hiding in the dark won't save you.",
        "challenger_reply": "My eyes are locked on your every step. Show me your speed!",
        "victory_epilogue": "Shadow dissolves into a wisp of vapor with a quiet nod of respect: 'Your senses are sharper than the darkness.'",
    },
    {
        "id": 4,
        "title": "The Gilded Duelist",
        "opponent": "Golden",
        "arena": "Frozen Peak",
        "difficulty": "MEDIUM",
        "level_offset": 3,
        "reward_coins": 120,
        "story_paragraphs": [
            "On the snow-swept crags of Frozen Peak, the icy wind howls around an ancient stone dais overlooking the tournament grounds.",
            "Awaiting {warrior} is Golden, the tactical master. Clad in ornate gilded armor, he reads muscle tension and breath, formulating counters before an attack even launches.",
            "This battle will test discipline and deception. A single predictable strike will be ruthlessly parried and punished."
        ],
        "intro_quote": "Every stance has a counter. Every champion has a flaw. Let us measure yours.",
        "challenger_line": "So you're the tactical grandmaster of the Frozen Peak. Ready to have your calculations shattered?",
        "challenger_reply": "Try reading this! I don't plan on holding back!",
        "victory_epilogue": "Golden lowers his rapier, brushing fresh snow from his mantle: 'Superb form. You may yet reach the Sovereign's seat.'",
    },
    {
        "id": 5,
        "title": "Crimson Reckoning",
        "opponent": "Crimson",
        "arena": "Dojo",
        "difficulty": "HIGH",
        "level_offset": 4,
        "reward_coins": 150,
        "story_paragraphs": [
            "Humiliated by his earlier defeat, Crimson has shattered tournament protocol, breaking through the sacred Dojo barriers to demand vengeance.",
            "His eyes burn with furious madness, his twin blades imbued with bloodlust. He fights without self-preservation, striking with blistering fury.",
            "{warrior} must weather a savage storm of strikes and deliver the decisive counter to permanently silence the berserker."
        ],
        "intro_quote": "I won't be disgraced twice! I'll tear you limb from limb!",
        "challenger_line": "Back for a second beating, Crimson? Blind rage won't change the outcome.",
        "challenger_reply": "Bring all the fury you have left—I'll put it out for good!",
        "victory_epilogue": "Crimson's blades shatter on the tatami mats as he falls, his wild fury finally broken.",
    },
    {
        "id": 6,
        "title": "The Unbreakable Colossus",
        "opponent": "Steel",
        "arena": "Temple Ruins",
        "difficulty": "HIGH",
        "level_offset": 5,
        "reward_coins": 180,
        "story_paragraphs": [
            "At the threshold of the Grand Sanctum, Steel has undergone an arcane reinforcement, forged with enchanted siege metal.",
            "His armor absorbs massive impacts without flinching, and his counter-swings hit with the force of falling boulders.",
            "Every blow {warrior} strikes must be carefully chosen to chip away at this living fortress before his crushing strength ends the match."
        ],
        "intro_quote": "Reinforced and immovable. You shall shatter against my ramparts.",
        "challenger_line": "Enchanted siege armor? You still move like a statue, Steel.",
        "challenger_reply": "The Sanctum doors are right behind you, and I'm going through!",
        "victory_epilogue": "Massive iron plates crack and crash to the cobblestone floor as Steel's furnace vents white steam in defeat.",
    },
    {
        "id": 7,
        "title": "Nightfall Ambush",
        "opponent": "Shadow",
        "arena": "Underground Vault",
        "difficulty": "HELL",
        "level_offset": 6,
        "reward_coins": 220,
        "story_paragraphs": [
            "The final passageway plunges into total subterranean darkness. Torches sputter out one by one as chilled air floods the vault.",
            "Shadow returns, operating at the peak of his lethal art. Unhindered by sight, he darts across walls and phases through attacks with ethereal speed.",
            "To reach the Grand Sovereign, {warrior} must fight with instincts alone, anticipating lethal strikes from the void."
        ],
        "intro_quote": "Welcome to your grave. The darkness swallows all champions.",
        "challenger_line": "Killing the torches won't save you, Shadow. I can hear your breath in the dark.",
        "challenger_reply": "One final strike decides who walks out of this vault alive!",
        "victory_epilogue": "A blinding strike dispels the gloom. Shadow staggers back, admitting: 'The Sovereign awaits... your blade is true.'",
    },
    {
        "id": 8,
        "title": "The Grand Sovereign (FINAL BOSS)",
        "opponent": "Golden",
        "arena": "Frozen Peak",
        "difficulty": "HELL",
        "level_offset": 8,
        "reward_coins": 400,
        "story_paragraphs": [
            "At the highest pinnacle above the clouds stands the Grand Sovereign's throne. The entire realm stretches out below in golden sunlight.",
            "The Sovereign—the pinnacle of the Golden Vanguard—wields perfect balance, ruthless counters, and supreme command of the arena. No fighter has ever bested him in duel.",
            "The tournament crown, the championship prize, and eternal legend are on the line. {warrior}, unleash everything you have learned!"
        ],
        "intro_quote": "You have carved a bloody trail to my sanctum. Now show me if you are worthy of the Sovereign Crown!",
        "challenger_line": "I've fought through every guardian in your citadel, Sovereign. The crown is mine!",
        "challenger_reply": "Enough words—let the final duel begin!",
        "victory_epilogue": "The Grand Sovereign drops his blade, the arena echoing with thunderous cheers! {warrior} is crowned the undisputed Grand Champion of Arena-AI!",
    },
]


def get_battle(battle_id: int) -> Dict[str, Any]:
    """Retrieve battle configuration by 1-based index."""
    for b in CAMPAIGN_BATTLES:
        if b["id"] == battle_id:
            return b
    return CAMPAIGN_BATTLES[0]


def format_story_paragraphs(battle: Dict[str, Any], warrior_name: str) -> List[str]:
    """Interpolate the player warrior's name into the dark-fantasy storyline."""
    paras = battle.get("story_paragraphs", [])
    return [p.format(warrior=warrior_name) for p in paras]


def get_battle_dialogue(battle: Dict[str, Any], warrior_name: str) -> List[Dict[str, str]]:
    """Build a structured visual-novel / comic face-off script for a campaign battle.

    Returns an ordered list of steps:
      1. Scene Narration (stage-setting lore banner)
      2. Challenger Opening Line (left character speech bubble)
      3. Opponent Challenge Quote (right character speech bubble)
      4. Challenger Battle Retort (left character speech bubble)
    """
    paras = format_story_paragraphs(battle, warrior_name)
    opponent = battle.get("opponent", "Crimson")

    scene_narration = paras[0] if paras else "The arena gates open as two contenders step onto the stone floor."
    if len(paras) > 1:
        scene_narration = f"{paras[0]} {paras[1]}"

    challenger_line = battle.get(
        "challenger_line",
        f"Stand ready, {opponent}. I didn't come this far to turn back now!",
    ).format(warrior=warrior_name, opponent=opponent)

    opponent_quote = battle.get(
        "intro_quote",
        "Show me if your resolve matches your words, contender!",
    ).format(warrior=warrior_name, opponent=opponent)

    challenger_reply = battle.get(
        "challenger_reply",
        paras[-1] if len(paras) > 2 else "Enough talk—let our fists decide!",
    ).format(warrior=warrior_name, opponent=opponent)

    return [
        {
            "type": "narration",
            "speaker": "SCENE NARRATION",
            "side": "center",
            "pose_left": "idle",
            "pose_right": "idle",
            "text": scene_narration,
        },
        {
            "type": "dialogue",
            "speaker": warrior_name.upper(),
            "side": "left",
            "pose_left": "idle",
            "pose_right": "idle",
            "text": challenger_line,
        },
        {
            "type": "dialogue",
            "speaker": opponent.upper(),
            "side": "right",
            "pose_left": "idle",
            "pose_right": "idle",
            "text": opponent_quote,
        },
        {
            "type": "dialogue",
            "speaker": warrior_name.upper(),
            "side": "left",
            "pose_left": "idle",
            "pose_right": "idle",
            "text": challenger_reply,
        },
    ]
