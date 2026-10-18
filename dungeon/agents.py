"""ADK agents: the live Game Master and the specialists it leans on."""
import hashlib
import json
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types
from pydantic import BaseModel, Field

from . import config, content, forge, names, premise, tools


# --- specialists -----------------------------------------------------------

class NpcReply(BaseModel):
    line: str = Field(description="What the NPC says, in their own voice. 1-3 sentences.")
    mood: str = Field(description="One or two words for how they feel right now.")
    disposition_change: int = Field(description="-25 to 15. How this exchange changes their opinion of the player.")
    remember: str = Field(description="One short sentence the NPC will remember about this exchange.")
    share_secret: Optional[str] = Field(None, description="id of a secret they reveal in this line, or null")
    offer_quest: Optional[str] = Field(None, description="id of a quest they ask the player to do in this line, or null")
    turn_hostile: bool = Field(False, description="True only if they attack or draw a weapon now.")
    suggested_replies: list[str] = Field(description="Three short things the player might say next, varied in tone.")


class Feature(BaseModel):
    name: str
    description: str


class ExitHint(BaseModel):
    direction: str = Field(description="north, south, east, west, up or down")
    hint: str = Field(description="What the way onward looks like, without naming the destination.")


ARCH_ITEMS = ", ".join(forge.ITEM_ARCHETYPES)
ARCH_MONSTERS = ", ".join(forge.MONSTER_ARCHETYPES)
TYPES = ", ".join(content.DAMAGE_TYPES)


class Block(BaseModel):
    kind: str = Field(description="one of: " + ", ".join(forge.BLOCKS) +
                      ". damage/status/push/chain hit foes; heal/shield/cure/escape/summon are for yourself")
    damage_type: Optional[str] = Field(None, description="for damage or chain: one of " + TYPES)
    status: Optional[str] = Field(None, description="for status: on foes one of " + ", ".join(forge.BAD) +
                                  "; on yourself one of " + ", ".join(forge.GOOD))


class GenAbility(BaseModel):
    name: str = Field(description="Evocative, fits the setting.")
    description: str = Field(description="One sentence of flavour, no numbers.")
    target: str = Field(description="enemy, all_enemies or self")
    blocks: list[Block] = Field(description="1-3 building blocks. More blocks means each is weaker.")


class GenItem(BaseModel):
    name: str
    description: str = Field(description="One sentence of flavour, no numbers.")
    archetype: str = Field(description="one of: " + ARCH_ITEMS)
    tier: int = Field(description="1 common, 2 fine, 3 rare")
    damage_type: Optional[str] = Field(None, description="weapons, focuses and bombs: one of " + TYPES)
    on_hit_status: Optional[str] = Field(None, description="weapons only, optional: " + ", ".join(forge.ON_HIT))
    resist: Optional[str] = Field(None, description="armour or trinket only, optional: a non-physical damage type")
    bonus: Optional[str] = Field(None, description="trinkets: hit, ac, max_hp or resist")
    use: Optional[GenAbility] = Field(None, description="bombs, tonics and scrolls: what it does (a scroll teaches it)")


class GenMonster(BaseModel):
    name: str
    description: str = Field(description="One sentence: what it looks like and how it fights.")
    archetype: str = Field(description="one of: " + ARCH_MONSTERS)
    tier: int = Field(description="1 for early fights, 2 tougher, 3 deadly. Bosses are 2 or 3.")
    damage_type: str = Field(description="its normal attack, one of " + TYPES)
    resist: Optional[str] = Field(None, description="optional, a non-physical damage type it shrugs off")
    weak: Optional[str] = Field(None, description="a damage type that hurts it more. Needed if it resists anything.")
    abilities: list[GenAbility] = Field(description="1-2 signature abilities")
    loot: list[str] = Field(description="0-1 names of items from your items list it might drop")


class EncounterRef(BaseModel):
    monster: str = Field(description="name of a monster from the monsters list")
    count: int = Field(description="1, or up to 3 for a swarm")


class NewNpc(BaseModel):
    name: str
    role: str
    personality: str
    voice: str
    goals: list[str]
    secret: str
    disposition: int = Field(description="10-70, how they feel about strangers")
    fights_as: str = Field(description="if it comes to blows: a monster archetype (" + ARCH_MONSTERS + ") or a monster name")


class NewPlace(BaseModel):
    name: str
    description: str = Field(description="2-3 sentences, concrete and sensory.")
    features: list[Feature] = Field(description="1-3 things worth inspecting")
    exits: list[ExitHint] = Field(description="0-2 ways onward, not back the way the player came")
    new_monsters: list[GenMonster] = Field(description="0-1 new monsters native to this place")
    new_items: list[GenItem] = Field(description="0-1 new items found here")
    items: list[str] = Field(description="0-2 item names lying here (from the world's items or your new ones)")
    encounter: list[EncounterRef] = Field(description="0-2 foes by name, or empty if the place is safe")
    encounter_text: str
    npc: Optional[NewNpc] = None


class StartPlace(BaseModel):
    direction: str = Field(description="north, east, south or west of the starting place, each used once")
    name: str
    description: str = Field(description="2-3 sentences, concrete and sensory.")
    features: list[Feature] = Field(description="1-2 things worth inspecting")
    items: list[str] = Field(description="0-2 names from your items list (tier 1 only)")
    encounter: list[EncounterRef] = Field(description="0-2 tier 1 foes, or empty if the place is safe")
    encounter_text: str = Field(description="One sentence for when the foes appear. Empty if safe.")
    rest: bool = Field(description="True if the player could safely sleep here, like an inn")


class StartNpc(NewNpc):
    where: str = Field(description="'start', or the direction of the place they are in")
    sells: list[str] = Field(description="0-4 names from your items list they would sell")


class QuestHook(BaseModel):
    title: str
    desc: str = Field(description="One or two sentences: what needs doing and why.")
    giver: str = Field(description="name of the npc who offers it")
    kind: str = Field(description="'defeat' (beat some foes) or 'find' (bring an item back to the giver)")
    monster: Optional[str] = Field(None, description="for defeat: name of a tier 1 monster; put it in a place")
    item: Optional[str] = Field(None, description="for find: name of an item from your list")
    reward_ability: Optional[GenAbility] = Field(None, description="a technique the giver teaches as a reward")


class BossLair(BaseModel):
    direction: str = Field(description="which opening place it lies beyond: the direction of that place from the start")
    approach_name: str = Field(description="the dangerous stretch on the way to the boss")
    approach_description: str = Field(description="2 sentences, concrete and sensory")
    approach_encounter_text: str = Field(description="one sentence for when the guards on the way appear")
    lair_name: str = Field(description="where the boss lives")
    lair_description: str = Field(description="2 sentences, concrete and sensory")
    boss_intro: str = Field(description="one sentence for when the boss appears")
    gate_text: str = Field(description="one sentence of why a newcomer shouldn't go yet, in the world's own terms")
    rumour: str = Field(description="one sentence locals say about the boss, which hints where it is")
    quest_title: str = Field(description="a short title for the job of ending the boss")


class StartPlaceCore(BaseModel):
    name: str
    description: str = Field(description="2-3 sentences, concrete and sensory, setting the tone.")
    features: list[Feature] = Field(description="1-3 things worth inspecting")
    items: list[str] = Field(description="0-1 names from your items list")


class Opening(BaseModel):
    setting_name: str = Field(description="Short name for the world or place the story is set in.")
    tone: str = Field(description="A few words on the mood, e.g. 'tense, witty, rain-soaked'.")
    blurb: str = Field(description="2 sentences of background the other storytellers need to stay consistent.")
    starting_weapon: GenItem = Field(description="the player's own tier 1 weapon, suited to the setting, with an "
                                     "on_hit_status that fits it (a hook that bleeds, a torch that burns)")
    starting_consumable: GenItem = Field(description="a tier 1 healing draught the player starts with, named and "
                                         "flavoured for this world (archetype potion)")
    items: list[GenItem] = Field(description="5-8 items native to this world across tiers: weapons, armour (one tier 2 "
                                "piece), a potion, a bomb or tonic, a trinket and a scroll")
    monsters: list[GenMonster] = Field(description="exactly 4-6 monsters: 2-3 tier 1 for the opening, 1-2 tier 2, and one boss (tier 2)")
    boss_lair: BossLair = Field(description="where the boss lives: two steps beyond one of the opening places")
    start: StartPlaceCore
    places: list[StartPlace] = Field(description="2-3 places next to the start")
    npcs: list[StartNpc] = Field(description="2-3 people, at least one at the start")
    quest: QuestHook
    unexplored: list[ExitHint] = Field(description="1-2 ways from the start that lead somewhere not built yet")


class Rename(BaseModel):
    old: str
    new: str = Field(description="a fresh name in the same style and setting")


class Fixup(BaseModel):
    monsters: list[GenMonster] = Field(description="the extra monsters asked for, no more")
    renames: list[Rename] = Field(description="one new name for each name listed under rename")


class ScribeNotes(BaseModel):
    entries: list[str] = Field(description="0-2 short journal lines worth keeping. Empty if nothing new happened.")


def _text_only(callback_context, llm_request):
    # AgentTool runs these inside the live invocation and passes its RunConfig
    # down, which asks for AUDIO. These are ordinary text models, so undo that.
    llm_request.config.response_modalities = None
    llm_request.config.speech_config = None
    return None


def _background_model():
    return Gemini(model=config.BACKGROUND_MODEL,
                  retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2))


NAMING = (
    "Names: make them belong to this premise and nowhere else. Draw on the setting's own language, trades, "
    "geography, religion and slang (a drowned city's people might be named for tides and saints; a starship's crew "
    "for call signs and ranks). Mix forms: titles, nicknames, surnames, compound names. Avoid generic fantasy "
    "names; never use any of these: " + ", ".join(names.COMMON) + ". No two things share a name."
)


dialogue_agent = LlmAgent(
    name="dialogue_agent",
    model=_background_model(),
    description="Voices one NPC in conversation and decides how they react.",
    instruction=(
        "You play a single non-player character in a story game. The request gives the setting; stay true to it. "
        "You are given the NPC's profile, what they remember about the player, their current disposition (0-100) "
        "and what the player just said, plus the result of any dice check.\n"
        "Stay in character and in their voice. UK English. Keep the line to 1-3 sentences.\n"
        "Rules:\n"
        "- Only reveal a secret from secrets_you_could_share if their disposition is at least its needs_disposition, "
        "or a persuade check just succeeded. Put its id in share_secret and work it into the line.\n"
        "- Offer a quest from quests_you_can_offer when it fits naturally; put its id in offer_quest.\n"
        "- Rudeness, threats and accusations lower disposition. Kindness, help and fair dealing raise it.\n"
        "- turn_hostile only if they would really attack now. Most people walk away or refuse first.\n"
        "- If they sell things, mention a price from the sells list when asked. Never invent items.\n"
        "- suggested_replies: three short options the player could say next (friendly, practical, edgy)."
    ),
    output_schema=NpcReply,
    before_model_callback=_text_only,
)

creator_agent = LlmAgent(
    name="creator_agent",
    model=_background_model(),
    description="Builds a new location when the player goes somewhere unexplored.",
    instruction=(
        "You build one new location for a story game. The request gives the setting, where the player is coming "
        "from, the direction, what the way looked like, the danger tier of the new place, and the monsters and "
        "items this world already has. Make a place that fits that description, the setting and its tone.\n"
        "You can reuse the world's monsters and items by name, or invent at most one new monster and one new item "
        "native to this place. You pick names, flavour, archetype, tier and effect blocks; the game sets every "
        "number, so never write numbers. Keep new things at or below the danger tier. A new monster should play "
        "differently from the ones the world already has: a different archetype, damage type or signature.\n"
        "About half of places should have no encounter. Add an npc only sometimes (roughly one place in three). "
        "Give people and monsters distinctive names that suit the setting.\n" + NAMING
    ),
    output_schema=NewPlace,
    before_model_callback=_text_only,
)

opening_agent = LlmAgent(
    name="creator_opening",
    model=_background_model(),
    description="The Creator's first job: builds the opening of a new game from the player's premise.",
    instruction=(
        "You build the opening of a story game from the premise the player wrote. Make a starting place, 2-3 places "
        "around it, 2-3 people with clear personalities and wants, and one quest hook, all fitting the premise and "
        "its tone.\n"
        "Invent this world's own gear and monsters too. For each you write the name and flavour and choose an "
        "archetype, a tier and a few effect building blocks; the game turns those into numbers, so never write "
        "numbers or stats. Make the monsters fight differently from each other: mix archetypes, damage types, "
        "weaknesses and signature abilities (a caster that blinds, a swarm that poisons, a tank that wards itself, "
        "a boss that summons). Always make 4-6 monsters, and exactly one boss. Put only tier 1 monsters in the "
        "opening places; the tougher ones wait further out, and the boss lives in its lair, two steps beyond one of "
        "the opening places, which the quest hook should point towards. Keep at least one place without foes. The "
        "quest giver should be at the start. The starting weapon and draught are the player's own, so make them "
        "feel personal and of this world. UK English. Never mention game mechanics in descriptions.\n" + NAMING
    ),
    output_schema=Opening,
    before_model_callback=_text_only,
)

fixup_agent = LlmAgent(
    name="creator_fixup",
    model=_background_model(),
    description="Tops up an opening that came back short and renames anything too generic.",
    instruction=(
        "You patch the opening of a story game. The request gives the setting, the monsters it already has, how "
        "many more monsters of each kind are needed, and names that need changing with the reason. Make exactly the "
        "monsters asked for, native to the setting and different from the ones it has (archetype, damage type, "
        "signature). A boss is archetype boss, tier 2. You pick names, flavour, archetype, tier and effect blocks; "
        "never write numbers. For each name to change, give a new one in the same role and style.\n" + NAMING
    ),
    output_schema=Fixup,
    before_model_callback=_text_only,
)

scribe_agent = LlmAgent(
    name="scribe_agent",
    model=_background_model(),
    description="Keeps the journal in step with the story.",
    instruction=(
        "You keep the player's journal for a text adventure. You get the last few lines of narration and the "
        "existing journal. Write at most two short lines (under 20 words each) for genuinely new facts, clues or "
        "story beats that are not already in the journal. Plain past tense, UK English. If nothing new, return none."
    ),
    output_schema=ScribeNotes,
    before_model_callback=_text_only,
)

dialogue_tool = AgentTool(agent=dialogue_agent)
creator_tool = AgentTool(agent=creator_agent)


def _setting(tool_context):
    return premise.setting_text({"meta": tool_context.state.get("meta")})


async def ask_dialogue(tool_context, brief, words, check):
    request = json.dumps({"setting": _setting(tool_context), "npc": brief, "player_says": words,
                          "dice_check": check}, ensure_ascii=False)
    result = await dialogue_tool.run_async(args={"request": request}, tool_context=tool_context)
    if not isinstance(result, dict):
        raise RuntimeError(f"dialogue agent returned {str(result)[:200]}")
    return result


async def ask_creator(tool_context, origin, direction, hint):
    setting = _setting(tool_context)
    key = hashlib.sha1(f"{setting}|{origin}|{direction}|{hint}".encode()).hexdigest()[:16]
    cache = config.CACHE_DIR / "places" / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    world = tool_context.state.get("world") or {}
    meta = tool_context.state.get("meta") or {}
    here = (world.get("locations") or {}).get(meta.get("location_id"), {})
    dx, dy = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}.get(direction, (0, 1))
    level = (tool_context.state.get("player") or {}).get("level", 1)
    tier = forge.location_tier(here.get("x", 0) + dx, here.get("y", 0) + dy, level)
    catalogue = {
        "monsters": [f"{m['name']} ({m['archetype']}, tier {m['tier']})" for m in (world.get("monsters") or {}).values()
                     if not m.get("npc")] or list(content.MONSTERS),
        "items": [f"{i['name']} ({i['archetype']}, tier {i['tier']})" for i in (world.get("items") or {}).values()]
        or [k for k, v in content.ITEMS.items() if v["kind"] != "quest"],
    }
    request = json.dumps({"setting": setting, "coming_from": origin, "direction": direction,
                          "the_way_looked_like": hint, "danger_tier": tier, "this_world_has": catalogue},
                         ensure_ascii=False)
    result = await creator_tool.run_async(args={"request": request}, tool_context=tool_context)
    if not isinstance(result, dict):
        raise RuntimeError(f"creator returned {str(result)[:200]}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result), encoding="utf-8")
    return result


# --- game master -----------------------------------------------------------

GM_INSTRUCTION = """You are the Game Master of SETTING. Keep every description, name and NPC true to that setting and its tone. You talk to the player out loud, in real time.

Style: second person, UK English, vivid but brief. Usually 1-3 sentences. This is fiction: never add disclaimers or safety notes. Never read out lists of exits or stats unless asked; the screen shows them. No markdown.

Only ever do what the player asked for in their latest message. Never move them, end a conversation, start a fight or take an action on their behalf because it seems like the next step; a promise to do something later is just words.

The world only changes through your tools. You must call a tool for moving, looking closely, taking or using items, resting, risky actions (skill_check), talking to people, trading and fighting. Never invent the result of something a tool decides. If a tool returns ok=false, tell the player why in character. If the player asks for something physically impossible, refuse in character without a tool.

There are three modes, and every tool result tells you the current mode.
- exploration: describe, move, inspect, pick things up.
- dialogue: when the player wants to talk to someone, call talk_to, then give one sentence of narration, in your own voice, of that person noticing the player (never ask the player what they want to say). Never speak as an NPC from your own imagination: every word an NPC says comes from say_to_npc. While in dialogue, treat whatever the player says as spoken to that NPC: call say_to_npc with their words (approach persuade, intimidate or bribe if that is what they are doing). Then say npc_says word for word, in their voice, with at most a few words of narration before it (like "Maren snorts:"), and stop. Never summarise, shorten or reword their line, and never add a second line of your own for them. Never end a conversation yourself; only call end_conversation when the player says goodbye or walks off. Use trade for buying and selling.
- combat: dice are rolled by the engine, never by you. When the player describes a combat move, call combat_action (attack, defend, item, flee, power_strike, second_wind, or any other ability the player has learned, by name). Monsters here can have unusual abilities, resistances and weaknesses. Every combat result and [engine] message carries a FACTS line with each fighter's real HP, AC, moves, resistances and weaknesses. Use only those facts and the log: never invent a resistance, immunity, weakness, number or ability, and if the facts say "resists: nothing", nothing shrugs anything off. When the log says something was resisted or hit a weak spot, make it vivid. Narrate the log you get back, hits and misses and what the enemies did, in 2-3 punchy sentences, and say whose turn it is. On victory, mention the loot. On defeat, describe the fall and tell them they can load a save.

Messages that start with [engine] are things the player did with the on-screen buttons; the engine has already resolved them. Narrate the result in 1-3 sentences and do not call a tool for them.
Messages that start with [start new] mean a brand-new game: the player has only just arrived, has never been here and has met nobody. Set the scene by name in 2-3 sentences. Never say "welcome back", "again" or "return", and never refer to earlier visits or events.
Messages that start with [start loaded] mean a saved game was just loaded: welcome the player back by name and remind them where they are, in 2-3 sentences.

SESSION"""


GM_TOOLS = [tools.look_around, tools.move, tools.inspect, tools.take_item, tools.drop_item, tools.use_item,
            tools.rest, tools.skill_check, tools.talk_to, tools.say_to_npc, tools.trade, tools.give_item,
            tools.end_conversation, tools.attack, tools.combat_action]


SESSION_NEW = ("This session started as a brand-new game: before it, the player had never been in this world. "
               "Anything they know comes from this conversation.")
SESSION_LOADED = "This session started from a loaded save, so the player has been in this world before."


def gm_instruction(ctx):
    # an instruction provider, so each game gets its own setting and new/loaded context from session state
    meta = ctx.state.get("meta") or {}
    session = SESSION_LOADED if meta.get("origin") == "loaded" else SESSION_NEW
    return (GM_INSTRUCTION.replace("SETTING", premise.setting_text({"meta": meta}), 1)
            .replace("SESSION", session, 1).rstrip())


def make_game_master(model_name, live=True):
    if live:
        model = Gemini(model=model_name, speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.VOICE))))
    else:
        model = Gemini(model=model_name, retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2))
    return LlmAgent(
        name="game_master",
        model=model,
        description="Runs the game and talks to the player.",
        instruction=gm_instruction,
        tools=GM_TOOLS,
    )
