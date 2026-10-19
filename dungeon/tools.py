"""Function tools for the Game Master. Each one loads the game from session
state, runs a rule from the engine and writes back whatever changed."""
import logging

from google.adk.tools.tool_context import ToolContext

from . import combat, dialogue, names, people, quests, state, world
from .state import GameError

log = logging.getLogger(__name__)


def _run(tool_context, fn):
    g = state.load(tool_context.state)
    if not g["meta"]:
        return {"ok": False, "refused": "No game is loaded."}
    d = state.dice(g)
    try:
        result = fn(g, d) or {}
    except GameError as exc:
        return {"ok": False, "refused": str(exc), "mode": g["mode"]}
    state.store_dice(g, d)
    ticked = quests.sync(g)
    state.commit(tool_context.state, g)
    out = {"ok": True, **result, "mode": g["mode"]}
    if g.get("combat"):
        out["facts"] = combat.facts(g)
    return finish(g, out, ticked)


def finish(g, out, ticked=()):
    """Last touches on every tool result: objectives just done, and no names the player hasn't learned."""
    if ticked:
        out["objectives_done"] = [f"{title}: {text}" for title, text in ticked]
    strangers = people.brief(g)
    if strangers:
        out["strangers"] = (f"The player doesn't know the names of: {', '.join(strangers)}. Call them only that, "
                            "until they give their name in say_to_npc or someone names them.")
    return people.mask_deep(g, out)


def look_around(tool_context: ToolContext) -> dict:
    """Describe where the player is: the place, exits, people and items here."""
    return _run(tool_context, lambda g, d: world.describe(g))


async def move(direction: str, tool_context: ToolContext) -> dict:
    """Move the player. direction is a compass direction (north, south, east, west, up, down),
    'back', or the name of a place next to here."""
    from . import agents

    g = state.load(tool_context.state)
    try:
        attempt = world.move(state.load(tool_context.state), direction, state.dice(g))
    except GameError as exc:
        return {"ok": False, "refused": str(exc), "mode": g["mode"]}
    if "needs_creation" in attempt:
        need = attempt["needs_creation"]
        try:
            spec = await agents.ask_creator(tool_context, state.location(g)["name"], need["direction"], need["hint"])
        except Exception as exc:
            log.warning("creator failed: %s", exc)
            return {"ok": False, "refused": "The way is choked with smoke for now. Try again in a moment.",
                    "mode": g["mode"]}
        world_names = [n["name"] for n in g["world"]["npcs"].values()] + [l["name"] for l in g["world"]["locations"].values()]
        spec = names.clean_place(spec, world_names, seed=need["direction"] + state.location(g)["name"])

        def build(g, d):
            world.add_location(g, need["direction"], spec)
            return world.move(g, need["direction"], d)
        return _run(tool_context, build)
    return _run(tool_context, lambda g, d: world.move(g, direction, d))


def inspect(target: str, tool_context: ToolContext) -> dict:
    """Look closely at something or someone here, or an item the player carries."""
    return _run(tool_context, lambda g, d: world.inspect(g, target))


def take_item(item: str, tool_context: ToolContext) -> dict:
    """Pick up an item lying here."""
    return _run(tool_context, lambda g, d: world.take(g, item))


def drop_item(item: str, tool_context: ToolContext) -> dict:
    """Drop an item from the inventory here."""
    return _run(tool_context, lambda g, d: world.drop(g, item))


def use_item(item: str, tool_context: ToolContext) -> dict:
    """Use, drink or equip an item outside combat."""
    return _run(tool_context, lambda g, d: world.use_item(g, item, d))


def rest(tool_context: ToolContext) -> dict:
    """Pay for a bed and rest at an inn. Restores HP and abilities."""
    return _run(tool_context, lambda g, d: world.rest(g))


def skill_check(stat: str, difficulty: str, attempt: str, tool_context: ToolContext) -> dict:
    """Roll for a risky action that isn't combat, like climbing, sneaking or forcing a lock.
    stat is str, dex, con, int, wis or cha. difficulty is easy, medium, hard, very_hard or impossible."""
    return _run(tool_context, lambda g, d: world.skill_check(g, stat, difficulty, d, attempt))


def talk_to(npc: str, tool_context: ToolContext) -> dict:
    """Start a conversation with someone here. Switches to dialogue mode."""
    def go(g, d):
        result = dialogue.start(g, npc, d)
        if g["mode"] == "dialogue":
            result["npc"] = {k: v for k, v in dialogue.brief(g, g["dialogue"]["npc_id"]).items()
                             if k in ("name", "role", "voice", "attitude", "memory_of_player")}
            result["narrate"] = (f"One sentence, in your narrator's voice, of {result['npc']['name']} noticing the "
                                 f"player. Don't speak as them: their words only come from say_to_npc.")
        return result
    return _run(tool_context, go)


async def say_to_npc(words: str, tool_context: ToolContext, approach: str = "plain") -> dict:
    """Say something to the NPC the player is talking to. words is what the player says.
    approach is plain, persuade, intimidate or bribe (bribe costs 5 gold)."""
    from . import agents

    g = state.load(tool_context.state)
    if g["mode"] != "dialogue" or not g["dialogue"]:
        return {"ok": False, "refused": "The player isn't talking to anyone. Use talk_to first.", "mode": g["mode"]}
    nid = g["dialogue"]["npc_id"]
    d = state.dice(g)
    check = dialogue.social_check(g, nid, approach, d)
    try:
        reply = await agents.ask_dialogue(tool_context, dialogue.brief(g, nid), words, check)
    except Exception as exc:
        log.warning("dialogue agent failed: %s", exc)
        return {"ok": False, "refused": "They seem distracted and don't answer. Try again in a moment.", "mode": g["mode"]}
    try:
        effects = dialogue.apply_reply(g, nid, words, reply, check, d)
    except GameError as exc:
        return {"ok": False, "refused": str(exc), "mode": g["mode"]}
    state.store_dice(g, d)
    ticked = quests.sync(g)
    state.commit(tool_context.state, g)
    name = people.label(state.npc(g, nid))
    out = {"ok": True, "npc": name, "npc_says": reply.get("line"), "effects": effects, "mode": g["mode"],
           "speak_exactly": f"{name[0].upper() + name[1:]}: \"{reply.get('line')}\"",
           "how": "Say npc_says word for word in their voice. Don't shorten, reword or add to it."}
    if effects.get("learned_names"):
        out["names_learned"] = ("The player now knows: " + ", ".join(effects["learned_names"]) +
                                ". Use these names from now on.")
    if g.get("combat"):
        out["facts"] = combat.facts(g)
    if check:
        out["check"] = check
    return finish(g, out, ticked)


def trade(action: str, item: str, tool_context: ToolContext) -> dict:
    """Buy from or sell to the NPC the player is talking to. action is buy or sell."""
    return _run(tool_context, lambda g, d: dialogue.trade(g, action, item))


def give_item(item: str, npc: str, tool_context: ToolContext) -> dict:
    """Give an item to someone here, for example to finish a quest."""
    return _run(tool_context, lambda g, d: dialogue.give(g, npc, item))


def end_conversation(tool_context: ToolContext) -> dict:
    """Leave the conversation and go back to exploring."""
    def go(g, d):
        if g["mode"] != "dialogue":
            raise GameError("You aren't talking to anyone.")
        name = people.label(state.npc(g, g["dialogue"]["npc_id"]))
        world.end_dialogue(g)
        return {"left": name}
    return _run(tool_context, go)


def attack(target: str, tool_context: ToolContext) -> dict:
    """Attack someone. Starts a fight if there isn't one, otherwise attacks that enemy."""
    def go(g, d):
        if g["mode"] == "combat":
            return combat.player_action(g, "attack", d, target=target) | {"status": combat.summary(g)}
        nid = people.find_here(g, target)
        if not nid:
            raise GameError(f"There's nobody called '{target}' here to attack.")
        return dialogue.start_fight(g, nid, d, f"You go for {people.label(state.npc(g, nid))}!")
    return _run(tool_context, go)


def combat_action(action: str, tool_context: ToolContext, target: str = "", item: str = "") -> dict:
    """Take the player's turn in a fight. action is attack, defend, item, flee, power_strike, second_wind,
    or the name of any other ability the player knows (see their abilities). target is an enemy name
    (optional). item is needed for the item action."""
    def go(g, d):
        result = combat.player_action(g, action, d, target=target or None, item=item or None)
        return {**result, "status": combat.summary(g)}
    return _run(tool_context, go)
