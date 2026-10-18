"""ADK agents: the live Game Master and the specialists it leans on."""
import hashlib
import json
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types
from pydantic import BaseModel, Field

from . import config, content, premise, tools


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


class NewNpc(BaseModel):
    name: str
    role: str
    personality: str
    voice: str
    goals: list[str]
    secret: str
    disposition: int = Field(description="10-70, how they feel about strangers")
    fights_as: str = Field(description="one of: " + ", ".join(content.MONSTERS))


class NewPlace(BaseModel):
    name: str
    description: str = Field(description="2-3 sentences, concrete and sensory.")
    features: list[Feature] = Field(description="1-3 things worth inspecting")
    exits: list[ExitHint] = Field(description="0-2 ways onward, not back the way the player came")
    items: list[str] = Field(description="0-2 item ids from the allowed list")
    encounter: list[str] = Field(description="0-2 monster ids from the allowed list, or empty if the place is safe")
    encounter_text: str
    npc: Optional[NewNpc] = None


class Foe(BaseModel):
    template: str = Field(description="monster id from the allowed list; it decides the stats")
    name: str = Field(description="what this foe is called in this setting, e.g. 'Sky Pirate'")


class StartPlace(BaseModel):
    direction: str = Field(description="north, east, south or west of the starting place, each used once")
    name: str
    description: str = Field(description="2-3 sentences, concrete and sensory.")
    features: list[Feature] = Field(description="1-2 things worth inspecting")
    items: list[str] = Field(description="0-2 item ids from the allowed list")
    encounter: list[Foe] = Field(description="0-2 foes, or empty if the place is safe")
    encounter_text: str = Field(description="One sentence for when the foes appear. Empty if safe.")
    rest: bool = Field(description="True if the player could safely sleep here, like an inn")


class StartNpc(NewNpc):
    where: str = Field(description="'start', or the direction of the place they are in")
    sells: list[str] = Field(description="0-4 item ids they would sell, from the allowed list")


class QuestHook(BaseModel):
    title: str
    desc: str = Field(description="One or two sentences: what needs doing and why.")
    giver: str = Field(description="name of the npc who offers it")
    kind: str = Field(description="'defeat' (beat some foes) or 'find' (bring an item back to the giver)")
    monster: Optional[str] = Field(None, description="for defeat: the monster id to beat; put them in a place")
    item: Optional[str] = Field(None, description="for find: an item id from the allowed list")


class StartPlaceCore(BaseModel):
    name: str
    description: str = Field(description="2-3 sentences, concrete and sensory, setting the tone.")
    features: list[Feature] = Field(description="1-3 things worth inspecting")
    items: list[str] = Field(description="0-1 item ids from the allowed list")


class Opening(BaseModel):
    setting_name: str = Field(description="Short name for the world or place the story is set in.")
    tone: str = Field(description="A few words on the mood, e.g. 'tense, witty, rain-soaked'.")
    blurb: str = Field(description="2 sentences of background the other storytellers need to stay consistent.")
    start: StartPlaceCore
    places: list[StartPlace] = Field(description="2-3 places next to the start")
    npcs: list[StartNpc] = Field(description="2-3 people, at least one at the start")
    quest: QuestHook
    unexplored: list[ExitHint] = Field(description="1-2 ways from the start that lead somewhere not built yet")


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
        "from, the direction and what the way looked like. Make a place that fits that description, the setting "
        "and its tone.\n"
        f"Allowed item ids: {', '.join(content.ITEMS)}.\n"
        f"Allowed monster ids: {', '.join(content.MONSTERS)}. About half of places should have no encounter. "
        "Add an npc only sometimes (roughly one place in three)."
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
        "its tone. The game has simple rules underneath, so you can only use these:\n"
        f"Allowed item ids: {', '.join(content.ITEMS)}. Describe them however suits the setting.\n"
        f"Allowed monster ids (they decide the stats, you choose the name): "
        + "; ".join(f"{k} ({v['name']}, {v['hp']} hp, {v['ai']})" for k, v in content.MONSTERS.items()) + ".\n"
        "Keep at least one place without foes. The quest giver should be at the start. Give people distinctive "
        "names that suit the setting, not stock fantasy names like Elara or Silas. UK English. "
        "Never mention game mechanics in descriptions."
    ),
    output_schema=Opening,
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
    request = json.dumps({"setting": setting, "coming_from": origin, "direction": direction,
                          "the_way_looked_like": hint}, ensure_ascii=False)
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
- dialogue: when the player wants to talk to someone, call talk_to, then give one short greeting in that NPC's own voice (never ask the player what they want to say). While in dialogue, treat whatever the player says as spoken to that NPC: call say_to_npc with their words (approach persuade, intimidate or bribe if that is what they are doing). Then perform the NPC's line exactly as returned, in their voice, and stop. Never end a conversation yourself; only call end_conversation when the player says goodbye or walks off. Use trade for buying and selling.
- combat: dice are rolled by the engine, never by you. When the player describes a combat move, call combat_action (attack, defend, item, flee, power_strike, second_wind). Narrate the log you get back, hits and misses and what the enemies did, in 2-3 punchy sentences, and say whose turn it is. On victory, mention the loot. On defeat, describe the fall and tell them they can load a save.

Messages that start with [engine] are things the player did with the on-screen buttons; the engine has already resolved them. Narrate the result in 1-3 sentences and do not call a tool for them.
Messages that start with [start] mean a new or loaded game: greet the player by name and set the scene from the state given, in 2-3 sentences."""


GM_TOOLS = [tools.look_around, tools.move, tools.inspect, tools.take_item, tools.drop_item, tools.use_item,
            tools.rest, tools.skill_check, tools.talk_to, tools.say_to_npc, tools.trade, tools.give_item,
            tools.end_conversation, tools.attack, tools.combat_action]


def gm_instruction(ctx):
    # an instruction provider, so each game gets its own setting from session state
    return GM_INSTRUCTION.replace("SETTING", premise.setting_text({"meta": ctx.state.get("meta")}), 1)


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
