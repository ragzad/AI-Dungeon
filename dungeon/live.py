"""Runs a game session: the live Game Master connection, the text fallback,
button actions and the Scribe."""
import asyncio
import copy
import hashlib
import json
import logging
import uuid

from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from . import agents, combat, config, dialogue, premise, state, world
from .plugins import GamePlugin, is_quota_error
from .state import GameError

log = logging.getLogger(__name__)
USER = "player"


class Hub:
    """Owns the ADK services and every running session."""

    def __init__(self, live_models=None, text_model=None):
        self.session_service = InMemorySessionService()
        self.plugin = GamePlugin()
        self.live_models = list(live_models if live_models is not None else config.LIVE_MODELS)
        self.text_model = text_model or config.TEXT_MODEL
        self._runners = {}
        self.games = {}
        self.scribe_runner = Runner(app_name="scribe", agent=agents.scribe_agent,
                                    session_service=InMemorySessionService(), plugins=[self.plugin])
        self.scribe_runner.plugin_manager.set_skip_closing_plugins(True)
        self.opening_runner = Runner(app_name="opening", agent=agents.opening_agent,
                                     session_service=InMemorySessionService(), plugins=[self.plugin])
        self.opening_runner.plugin_manager.set_skip_closing_plugins(True)

    def runner(self, model, live):
        key = (model, live)
        if key not in self._runners:
            r = Runner(app_name=config.APP_NAME, agent=agents.make_game_master(model, live=live),
                       session_service=self.session_service, plugins=[self.plugin])
            r.plugin_manager.set_skip_closing_plugins(True)
            self._runners[key] = r
        return self._runners[key]

    async def opening(self, text):
        """Ask the Creator for an opening built around the player's premise.
        Cached on disk by premise, so the same idea doesn't cost another call."""
        key = hashlib.sha1(text.lower().encode()).hexdigest()[:16]
        cache = config.CACHE_DIR / "openings" / f"{key}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        s = await self.opening_runner.session_service.create_session(app_name="opening", user_id=USER)
        spec = None
        async for event in self.opening_runner.run_async(
                user_id=USER, session_id=s.id,
                new_message=types.Content(role="user", parts=[types.Part(text=json.dumps({"premise": text}))])):
            if event.content and event.content.parts and not event.partial:
                out = "".join(p.text or "" for p in event.content.parts if not p.thought)
                if out.strip():
                    spec = json.loads(out)
        if not isinstance(spec, dict):
            raise RuntimeError("the Creator returned no opening")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(spec), encoding="utf-8")
        return spec

    async def create(self, g):
        session = await self.session_service.create_session(app_name=config.APP_NAME, user_id=USER, state=g)
        self.plugin.watched.add(session.id)
        return session.id

    async def session(self, sid):
        session = await self.session_service.get_session(app_name=config.APP_NAME, user_id=USER, session_id=sid)
        if session is None:
            raise KeyError(sid)
        return session

    async def game(self, sid):
        return state.load((await self.session(sid)).state)

    async def apply(self, sid, fn):
        """Run an engine function against the session outside of an agent turn
        (button presses, the Scribe). Changes go in as an ADK event with a state delta."""
        session = await self.session(sid)
        g = state.load(session.state)
        d = state.dice(g)
        result = fn(g, d)
        state.store_dice(g, d)
        changed = state.delta(session.state, g)
        if changed:
            event = Event(author="engine", invocation_id=f"e-{uuid.uuid4().hex[:12]}",
                          actions=EventActions(state_delta=changed))
            await self.session_service.append_event(session, event)
            # a running live invocation holds its own Session object; bring it up to date
            for live in self.plugin.sessions.get(sid, []):
                if live is not session:
                    live.state.update(copy.deepcopy(changed))
        return result, g


def _used_line(name, r):
    if "equipped" in r:
        return f"{name} equips the {r['equipped']}" + (f" ({r['stats']})." if r.get("stats") else ".")
    if "learned" in r:
        return f"{name} studies the {r['used']} and learns {r['learned']}: {r['ability']}."
    if "healed" in r:
        return f"{name} uses the {r['used']} and recovers {r['healed']} HP."
    if "cured" in r:
        return f"{name} uses the {r['used']} and shakes off what ailed them."
    return f"{name} looks over the {r.get('item') or r.get('used')}."


def button_action(g, d, msg):
    """Buttons on the screen. Returns lines for the Game Master to narrate."""
    kind = msg.get("action")
    if kind in combat.ACTIONS or kind == "use_item":
        if kind == "ability" and g["mode"] != "combat":
            raise GameError("Abilities are for fights.")
        if g["mode"] != "combat":
            if kind in ("item", "use_item"):
                r = world.use_item(g, msg.get("item") or "", d)
                return [_used_line(g["player"]["name"], r)]
            raise GameError("You aren't in a fight.")
        r = combat.player_action(g, kind, d, target=msg.get("target"), item=msg.get("item"),
                                 ability=msg.get("ability"))
        return [e["text"] for e in r["events"]] + [combat.summary(g)]
    if kind == "end_conversation":
        if g["mode"] != "dialogue":
            raise GameError("You aren't talking to anyone.")
        name = state.npc(g, g["dialogue"]["npc_id"])["name"]
        world.end_dialogue(g)
        return [f"{g['player']['name']} ends the conversation with {name}."]
    if kind == "trade":
        r = dialogue.trade(g, msg.get("trade"), msg.get("item") or "")
        return [f"Trade: {json.dumps(r)}"]
    if kind == "rest":
        r = world.rest(g)
        return [f"Rested: {json.dumps(r)}"]
    if kind == "take":
        r = world.take(g, msg.get("item") or "")
        return [f"Picked up {r['took']}."]
    if kind == "dismiss":
        if g["combat"] and g["combat"].get("outcome"):
            g["combat"] = None
        return []
    raise GameError(f"Unknown action {kind}.")


class GameSession:
    def __init__(self, hub, sid, send):
        self.hub = hub
        self.sid = sid
        self.send = send  # async callable taking dict or bytes
        self.queue = None
        self.task = None
        self.mode = "connecting"
        self.model = None
        self.text_lock = asyncio.Lock()
        self.narration = []
        self.turns = 0
        self.scribe_every = 3
        self.closed = False
        self._spoke = False

    # --- lifecycle -----------------------------------------------------

    async def start(self, opener=None):
        self.queue = LiveRequestQueue()
        if opener:
            self._queue_text(opener)
        if self.hub.live_models and config.has_key():
            self.task = asyncio.create_task(self._live_loop())
        else:
            await self._go_text("No live model configured.")
            if opener:
                await self.send_text(opener, already_queued=True)

    async def close(self):
        self.closed = True
        if self.queue:
            self.queue.close()
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
        self.hub.plugin.sessions.pop(self.sid, None)

    def _queue_text(self, text):
        self._pending = text
        self.queue.send_content(types.Content(role="user", parts=[types.Part(text=text)]))

    # --- live ------------------------------------------------------------

    def _run_config(self):
        return RunConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(),
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=24000, sliding_window=types.SlidingWindow(target_tokens=12000)),
        )

    async def _live_loop(self):
        for model in self.hub.live_models:
            self.model = model
            got_events = False
            try:
                runner = self.hub.runner(model, live=True)
                await self.send({"type": "status", "engine": "live", "model": model})
                self.mode = "live"
                async for event in runner.run_live(user_id=USER, session_id=self.sid,
                                                   live_request_queue=self.queue, run_config=self._run_config()):
                    if event.error_code:
                        raise RuntimeError(f"{event.error_code}: {event.error_message}")
                    got_events = True
                    await self._on_event(event)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.closed:
                    return
                log.warning("live model %s failed: %s", model, str(exc)[:300])
                quota = is_quota_error(exc)
                if got_events:
                    await self.send({"type": "notice", "level": "warn",
                                     "text": "The Game Master lost the thread for a moment. Reconnecting..."})
                # the old queue may be half-consumed; start clean and resend the last thing the player said
                self.queue = LiveRequestQueue()
                if getattr(self, "_pending", None) and not got_events:
                    self.queue.send_content(types.Content(role="user", parts=[types.Part(text=self._pending)]))
                if quota:
                    continue
        await self._go_text("The Game Master's voice is spent for now (Live API quota or connection). "
                            "Carrying on in text.")
        if getattr(self, "_pending", None) and not self._spoke:
            await self.send_text(self._pending, already_queued=True)

    async def _on_event(self, event):
        if event.input_transcription and event.input_transcription.text:
            await self.send({"type": "you_said", "text": event.input_transcription.text,
                             "final": bool(event.input_transcription.finished)})
        out = event.output_transcription
        if out and out.text:
            self._spoke = True
            if event.partial:
                await self.send({"type": "token", "text": out.text, "author": event.author})
            else:
                await self.send({"type": "final", "text": out.text, "author": event.author})
                self.narration.append(out.text)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.inline_data and (part.inline_data.mime_type or "").startswith("audio/"):
                    await self.send(part.inline_data.data)
                elif part.text and not part.thought and not out:
                    # text models (fallback path) put text straight in content
                    kind = "token" if event.partial else "final"
                    await self.send({"type": kind, "text": part.text, "author": event.author})
                    if not event.partial:
                        self.narration.append(part.text)
            calls = event.get_function_calls()
            if calls:
                log.info("tool calls: %s", [(c.name, c.args) for c in calls])
                await self.send({"type": "tool", "names": [c.name for c in calls]})
            if event.get_function_responses():
                await self.push_state()
        if event.interrupted:
            await self.send({"type": "interrupted"})
        if event.turn_complete:
            await self.send({"type": "turn_complete"})
            await self._after_turn()

    # --- text fallback -------------------------------------------------

    async def _go_text(self, reason):
        self.mode = "text"
        self.model = self.hub.text_model
        await self.send({"type": "status", "engine": "text", "model": self.model})
        await self.send({"type": "notice", "level": "warn", "text": reason})

    async def _text_turn(self, text):
        async with self.text_lock:
            runner = self.hub.runner(self.hub.text_model, live=False)
            try:
                async for event in runner.run_async(
                        user_id=USER, session_id=self.sid,
                        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
                        run_config=RunConfig(streaming_mode=StreamingMode.SSE)):
                    if event.error_code:
                        raise RuntimeError(f"{event.error_code}: {event.error_message}")
                    await self._on_event(event)
            except Exception as exc:
                log.warning("text turn failed: %s", str(exc)[:300])
                msg = ("The spirits are exhausted (API quota). Wait a minute and try again. "
                       "Buttons still work." if is_quota_error(exc)
                       else "The Game Master stumbled over that. Try again.")
                await self.send({"type": "notice", "level": "error", "text": msg})
            await self.send({"type": "turn_complete"})
            await self._after_turn()

    # --- input -----------------------------------------------------------

    async def send_text(self, text, already_queued=False):
        text = text.strip()[:1000]
        if not text:
            return
        if self.mode == "text":
            asyncio.create_task(self._text_turn(text))
        elif not already_queued:
            self._queue_text(text)

    async def send_audio(self, data):
        if self.mode == "live" and self.queue:
            self.queue.send_realtime(types.Blob(data=data, mime_type="audio/pcm;rate=16000"))

    async def action(self, msg):
        try:
            lines, g = await self.hub.apply(self.sid, lambda g, d: button_action(g, d, msg))
        except GameError as exc:
            await self.send({"type": "notice", "level": "info", "text": str(exc)})
            return
        await self.push_state()
        if lines:
            await self.send({"type": "engine", "lines": lines})
            await self.send_text("[engine] " + " ".join(lines) + f" Mode is now {g['mode']}.")

    async def push_state(self):
        g = await self.hub.game(self.sid)
        await self.send({"type": "state", "state": state.public_view(g)})

    # --- scribe ------------------------------------------------------------

    async def _after_turn(self):
        self.turns += 1
        if self.scribe_every and self.turns % self.scribe_every == 0 and self.narration:
            recent = " ".join(self.narration[-6:])
            self.narration = self.narration[-2:]
            asyncio.create_task(self._scribe(recent))

    async def _scribe(self, recent):
        try:
            g = await self.hub.game(self.sid)
            prompt = json.dumps({"narration": recent, "journal": [e["text"] for e in g["journal"][-15:]]})
            s = await self.hub.scribe_runner.session_service.create_session(app_name="scribe", user_id=USER)
            notes = None
            async for event in self.hub.scribe_runner.run_async(
                    user_id=USER, session_id=s.id,
                    new_message=types.Content(role="user", parts=[types.Part(text=prompt)])):
                if event.content and event.content.parts and not event.partial:
                    text = "".join(p.text or "" for p in event.content.parts if not p.thought)
                    if text.strip():
                        notes = json.loads(text)
            entries = [str(e)[:160] for e in (notes or {}).get("entries", [])][:2]
            if entries:
                def add(g, d):
                    for e in entries:
                        state.journal(g, e, "story")
                await self.hub.apply(self.sid, add)
                await self.push_state()
        except Exception as exc:
            log.info("scribe skipped: %s", str(exc)[:200])


def opener(g, loaded=False):
    p = g["player"]
    loc = state.location(g)
    if loaded:
        return (f"[start] {p['name']} has loaded a saved game. They are at {loc['name']} in {g['mode']} mode, "
                f"{p['hp']}/{p['max_hp']} HP. Welcome them back and remind them where they are.")
    s = g["meta"].get("setting")
    if s:
        giver = next((g["world"]["npcs"][q["giver"]] for q in g["world"]["quests"].values()), None)
        hook = f" Hint that {giver['name']}, the {giver['role']}, might have work for them." if giver else ""
        return (f"[start] New game in {s['name']}, built from the player's premise: \"{s['premise']}\". "
                f"The player is {p['name']}. They are standing in {loc['name']}: {loc['desc']} "
                f"Set the scene in 2-3 sentences in the tone of the premise.{hook}")
    return (f"[start] New game. The player is {p['name']}, a sellsword arriving in Emberfall. "
            f"They are standing in {loc['name']}: {loc['desc']} Set the scene and hint that the tavern to the "
            f"north is where people talk.")
