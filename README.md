# AI Dungeon

A small dark fantasy game you play by talking to a Game Master. It speaks back out loud in real time, you can type or use your mic, and underneath it there's a proper rules engine, so fights, dice and NPC relationships are actually tracked rather than made up by the model.

On the start screen you can describe the adventure you want, like "a heist in a floating city" or "a haunted lighthouse", and the game builds an opening around it: where you start, who's there, what they want, a first job, your own starting weapon and draught, and a boss waiting a few places out. Or leave it blank (or tap "Surprise me") and you start in Emberfall, a village at the edge of a forest that burned and never quite stopped. There are a few people to talk to, a couple of quests, wolves at the edge of the woods, and new places get built as you walk into them.

![Exploring](docs/01-explore.png)

## Why I rebuilt it

The first version was a Streamlit app where five agents passed a JSON file around each turn. It worked, but every turn was four or five model calls, fights were whatever the model felt like, and everyone shared one `world_state.json`. I wanted something that felt like a game: dice rolled in code, a turn order, HP that goes down, NPCs who remember you, and a Game Master you can just talk to.

## How to play

- Type what you do, tap one of the suggestion chips, or press the mic and say it.
- **Exploring**: move around, look at things, pick things up. Exits, people and items show up as chips above the input. The map, character sheet and journal are in the side panel (the menu button on a phone).
- **Talking**: tap "Talk to Maren" (or just say you go and talk to her) and the screen switches to a conversation with her portrait, how much she likes you, and three suggested replies. What you say changes her opinion of you. Be nice and she might tell you things or give you work. Push someone too far and they'll go for you, which starts a fight.
- **Fighting**: HP bars at the top, big action buttons at the bottom: Attack, Defend, Item, Power Strike, Second Wind, any abilities you've picked up, and Flee. Tap an enemy's bar to target it. Every roll shows in the log with the numbers, and the Game Master narrates what happened. Win and you get XP and loot. Lose and you can load a save.
- Saving is the disk button at the top. The Gutter Lantern rents beds for 5 gold if you need to heal up.

| Talking | Fighting | After the fight |
| --- | --- | --- |
| ![Dialogue](docs/02-dialogue.png) | ![Combat](docs/03-combat.png) | ![Victory](docs/04-victory-or-journal.png) |

It's built phone first. On a phone the chat takes the whole screen, the combat buttons sit above the input where your thumb is, and the character sheet, map and journal slide out from the side.

| Your premise | The opening it builds |
| --- | --- |
| ![Premise](docs/05-premise.png) | ![Premise opening](docs/06-premise-opening.png) |

| Your premise | The opening it builds |
| --- | --- |
| ![Phone premise](docs/m05-premise.png) | ![Phone premise opening](docs/m06-premise-opening.png) |

A premise world gets its own monsters, gear and abilities. These are from a "lighthouse island where the fog eats ships" run. You start with a Rust-Bitten Harpoon (1d8, and it sometimes leaves foes bleeding) and two Lantern-Oil Tonics. Mist-Lurking Scrimshanders stitch your legs so you're slowed, and loot includes a Fog-Glass Phial that blinds everything it bursts over.

| A new game's opening and starting kit | The world's boss |
| --- | --- |
| ![Opening](docs/09-opening.png) | ![Boss](docs/10-boss.png) |

| A new game's opening | The world's boss |
| --- | --- |
| ![Phone opening](docs/m09-opening.png) | ![Phone boss](docs/m10-boss.png) |

| Generated monster and its signature move | Generated loot |
| --- | --- |
| ![Generated combat](docs/07-generated-combat.png) | ![Generated loot](docs/08-generated-loot.png) |

| Generated monster and its signature move | Generated loot |
| --- | --- |
| ![Phone generated combat](docs/m07-generated-combat.png) | ![Phone generated loot](docs/m08-generated-loot.png) |

| Exploring | Talking | Fighting |
| --- | --- | --- |
| ![Phone exploring](docs/m01-explore.png) | ![Phone dialogue](docs/m02-dialogue.png) | ![Phone combat](docs/m03-combat.png) |

There's also a short recording of a full session in [docs/demo.gif](docs/demo.gif).

## How it works

It's built on Google's [Agent Development Kit](https://google.github.io/adk-docs/) (ADK). The Game Master is an ADK agent running on the Gemini Live API, and everything that changes the world goes through function tools that call plain Python rules.

```mermaid
flowchart TD
    B[Browser<br>chat, buttons, mic] <-->|WebSocket<br>text, PCM audio, state| S[FastAPI server]
    S -->|LiveRequestQueue| GM[Game Master<br>LlmAgent on a Live model<br>runner.run_live]
    GM -->|streamed transcript + audio| S
    GM --> T[Function tools<br>move, inspect, take_item, talk_to,<br>say_to_npc, trade, attack, combat_action...]
    T --> E[Rules engine<br>world.py, dialogue.py, combat.py, dice.py]
    T -->|AgentTool| D[Dialogue agent<br>lite model, structured reply]
    T -->|AgentTool| C[Creator agent<br>lite model, new places]
    E <--> ST[(ADK session state<br>player, world, mode,<br>combat, dialogue, journal)]
    S -->|button presses| E
    S -.every few turns.-> SC[Scribe agent<br>lite model, journal notes]
    SC --> ST
```

- **Game Master** (`dungeon/agents.py`) is an `LlmAgent` with 15 function tools. It talks to you and decides which tool fits what you said, but it can't change anything itself. It narrates what the tools hand back.
  - It's told whether this is a brand-new game or a loaded save, so a new game doesn't open with "welcome back". If it says that anyway on a new game, the text on screen is corrected.
  - It never speaks for an NPC on its own. When you start talking to someone it just describes them noticing you, and their lines come from the Dialogue agent, which it's told to read out word for word.
  - Every combat result carries a FACTS line with each fighter's real HP, AC, moves, resistances and weaknesses, and it's told to use only those. After each turn its narration is checked for resistances or weaknesses the fight doesn't have, and if it made one up, a short "Rules check" note appears.
- **World keeper** is the old Archivist idea, done in code instead of a prompt (`dungeon/world.py`). Moving, inspecting, picking up, resting and skill checks are all validated against the state, so "I pick up the tavern" just fails.
- **Dialogue agent** plays one NPC at a time. It gets that NPC's personality, goals, what they remember about you, how much they like you (0 to 100), the secrets they could share and the quests they could offer. It replies with a line plus structured choices: how their opinion changes, whether they share a secret, offer a quest or turn hostile. `dungeon/dialogue.py` then applies those within the rules. A secret only comes out if they like you enough (or you just passed a persuade roll), and "turn hostile" is ignored unless the relationship has actually gone bad. Persuade and intimidate are real d20 rolls against your stats, and a bribe costs real gold.
- **Combat engine** (`dungeon/combat.py`) is plain Python: initiative, AC, to-hit and damage rolls, crits on a natural 20, Defend, items, Power Strike and Second Wind, Flee as a Dex check, status effects, damage types with resistances and weaknesses, enemies picking their own moves, then XP, loot and levelling. The dice are seeded and the roll count is saved, so loading a save carries on with the same sequence. The model only narrates the log.
- **Your premise** goes to the Creator first. It writes the opening (a starting place, two or three places around it, two or three people, a quest hook, 4 to 6 monsters including a boss and its lair, the world's gear, your starting weapon and draught, and a short note on setting and tone), and `dungeon/premise.py` checks all of it before it goes into the game: unknown items and monsters are dropped, the quest's target is made sure to exist, and there's always somewhere to rest.
  - If it comes back with too few monsters, no boss, or names that need changing, one cheap second call asks for just the missing monsters and new names. If that fails too, the game fills the gaps itself.
  - Names are checked against a list of stock fantasy names the model loves (Elara, Silas, Oakhaven, Vane, Thorne, Lyra and friends), against each other, and against people in the last few worlds you made. Anything caught gets renamed, and the new name is carried through to every description and quest that mentions it.
  - The boss lives two places beyond one of the opening places: a guarded approach, then its lair. Both are closed until you're level 2, and the map marks them. A piece of better gear lies on the way. Finishing the first job unlocks a quest to deal with the boss, and the journal and the locals tell you where to go. The first job's XP plus the opening fights get a normal player to level 2.
  - Your starting weapon is tier 1 but comes with a small perk, like a hook that leaves foes bleeding, so it holds up against Emberfall's sword. Your starting draught heals as much as Emberfall's potion. The premise and setting live in the session state, so saves keep them, and the Game Master, Dialogue agent and Creator all get told about it every time, in Live mode and in the text fallback. If the Creator can't build it (quota, or no key), you start in Emberfall and get told why.
- **Creator** builds a new location when you walk through an unexplored exit. It can reuse the world's monsters and items or add new ones. Results are cached on disk, so the same lane builds the same place without another API call.
- **The forge** (`dungeon/forge.py`) is how premise worlds get new content without the model being able to break the game. The Creator picks a name, a description, an archetype and a tier (1 to 3), and never writes a number. Python does the numbers.
  - Monsters are a brute, skirmisher, caster, swarm, beast, tank or boss, and each one plays differently. Brutes hit hard, skirmishers are hard to hit, casters lean on abilities, swarms come in numbers, tanks soak damage, and bosses fight alone with more HP and two uses of their moves. HP, AC, attack and XP come from a table for that archetype and tier.
  - Items are a light or heavy weapon, ranged weapon, focus, light or heavy armour, shield, potion, bomb, tonic, trinket or scroll, with stats from a budget for their tier.
  - Abilities are built from a small set of vetted blocks: damage of a type, hitting several targets or chaining, heal, shield, a status, push back, escape, cure, or summon (capped at four enemies on the field). Each extra block or target makes the dice smaller, so a move that does three things does each one less well.
  - The statuses are poisoned, burning, bleeding, stunned, weakened, blinded, slowed, regen, shielded and hasted. Damage types are physical, fire, frost, shock, poison, radiant, necrotic and psychic. A monster can resist at most one, never physical, and only if it also has a weakness.
  - Generated monsters get one or two signature abilities and an enemy AI that uses them sensibly (patch itself up or call for help when it gets hurt, use its signature moves while they last). Items can carry an on-hit effect or a use effect, scrolls and quest rewards can teach you an ability, and each world gets its own loot tables.
  - Anything that doesn't fit is repaired or dropped: unknown archetypes fall back to a sensible one, tiers are clamped, bosses only show up far enough out and when you've levelled, and encounters are fitted to a budget for that area.
  - Emberfall still uses the hand-made content, and old saves load as before.
- **Scribe** runs every few turns in the background and adds short story notes to the journal. Quest and combat entries come straight from the engine.

### ADK features used

- `LlmAgent` for the Game Master, Dialogue, Creator and Scribe agents. The specialists use `output_schema` with Pydantic models so their replies come back as data.
- Function tools with `ToolContext`. Every tool loads the game from `tool_context.state`, runs a rule and writes back only the keys that changed.
- `AgentTool` to call the Dialogue and Creator agents from inside tools. The nested run inherits the live run's audio settings, so those agents have a `before_model_callback` that switches them back to plain text.
- Session state through `InMemorySessionService`. Each game is its own ADK session, which fixes the old shared `world_state.json`.
- `Runner.run_live()` with a `LiveRequestQueue` for the realtime Game Master, with output and input transcription, session resumption and context window compression switched on in `RunConfig`.
- `Runner.run_async()` with `StreamingMode.SSE` as the fallback when no Live model is available.
- A plugin (`dungeon/plugins.py`) that retries background agents on a fallback model when they hit a 429, and keeps track of the session objects that live runs are using so button presses reach them.

### Live streaming

The Game Master runs on `gemini-3.8-live`, with `gemini-3.1-flash-live-preview` as the next one to try. Current Live models only answer in audio, so the text you see is the Live API's transcript of what the Game Master is saying. It comes through in small chunks of a few words, about 150 ms apart, at the same pace as the voice. The browser plays the 24 kHz PCM audio as it arrives and draws the transcript as it streams.

The mic button records 16 kHz PCM in the browser and sends it straight into the same `LiveRequestQueue`, so you can talk over the Game Master and it will stop and listen. Your own words show up as a transcript too.

Buttons such as Attack don't wait for the model. The server runs the rule straight away, writes the result into the session as an ADK event with a state delta, updates the screen, and then sends the Game Master an `[engine]` message to narrate.

## Running it

You need Python 3.12 or newer and a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

```
python -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # then put your key in .env
python server.py
```

Then open http://localhost:8010. The models can be changed in `.env` (see `.env.example`).

Or with Docker:

```
docker build -t ai-dungeon .
docker run -p 8010:8010 --env-file .env ai-dungeon
```

The mic needs either localhost or HTTPS, because browsers only allow microphone access on secure pages.

## Balance

`scripts/balance.py` makes random but valid worlds with the forge and plays them through the real combat engine with a simple sensible player (attack the weakest, use abilities and potions when it makes sense). It's deterministic, so the same run gives the same numbers. Across 100 generated worlds with 25 seeds each, I got:

| Fight | Win rate |
| --- | --- |
| Emberfall wolves, level 1 | 93.5% |
| Generated opening fights, level 1 | 94.3% |
| Same, with a quest reward ability | 94.3% |
| Tier 2 areas, level 2 | 88.2% |
| Tier 3 areas, level 3 | 93.6% |
| Bosses at level 3 | 94.2% |
| The lair's guarded approach, level 2 | 94.2% |
| The lair's boss, level 2 with the gear from the approach | 81.4% |

The lair rows play the actual boss route each generated world builds. The boss at level 2 is the hardest fight in the game on purpose.

```
python scripts/balance.py 100 25    # worlds, seeds
```

## Tests

```
pip install -r requirements-dev.txt
pytest
```

There are 144 tests. They cover the dice, combat rules (initiative, hits, crits, Defend, status effects, abilities, items, fleeing, victory, defeat, loot and levelling), moving between the three modes, building a world from a premise (and falling back when that fails), the forge (budgets, clamping, repair, abilities, loot tables, the enemy AI), a short balance run, the boss lair and its gate, the starting kit, topping up short openings and renaming stock names, what the Game Master is told (new or loaded game, NPC lines, combat facts) and the guards on what it says, NPC disposition, secrets, quests, trading and hostility, the ADK tools with the Dialogue and Creator agents faked, saving and loading, the HTTP endpoints and the quota fallbacks. Gemini is never called, and the key is removed from the environment during the run so nothing can reach it by accident. Coverage of the engine modules is around 90%.

## Known limitations

- The free tier is tight. Each thing you say is one Live turn, talking to an NPC adds one lite model call, and walking somewhere new adds one more. If the Live model runs out of quota, the game tells you and carries on in text with a normal model. If that runs out too, it tells you to wait a minute, and the combat buttons still work because they don't need the model.
- Audio is always generated, even with the speaker muted, because Live models don't do text-only output any more. That uses more quota than text would.
- Voice works in Chrome, Edge, Firefox and Safari on desktop and Android. On iPhone it needs iOS 14.5 or newer, and the phone has to be unmuted for the narration to play. Echo cancellation is left to the browser, so on a laptop without headphones the Game Master can sometimes hear itself.
- The Game Master is told to read NPC lines word for word, and in my tests it did, but it's a model and nothing can force it. Because it speaks the line as audio, it sometimes reads the "Maren Holt:" label out too.
- Sessions live in memory, so restarting the server ends any game that hasn't been saved. Saves are JSON files in `saves/`, and there's no login, so anyone who can reach the server can see the list.
- There's one character class and the world is small: four hand-made places plus whatever the Creator builds.
- Openings are cached by premise to save quota, so typing exactly the same premise again gives you the same world. Change a word to get a new one.
- Generated content is still built from a fixed set of archetypes and blocks, so a premise world plays differently but won't invent a brand new mechanic.
- The balance numbers come from the simulator, not from lots of real people playing. A reckless player will lose more often.
- Names are much better but not perfect. Only people's names are remembered between worlds, so two similar premises can still get the same item name (two of my lighthouse worlds both started with a Rust-Bitten Harpoon). Made-up replacement names, used when the model's rename fails, can sound a bit odd.
- The guards on the Game Master only fix the text. By the time a bad line is caught, the voice has already said it, so a made-up resistance gets a "Rules check" note rather than going unsaid. The check only looks for resistance and weakness claims, not every number.
- The boss route waits for level 2, but if you wander the opening for long enough you'll get there before finishing the first job. That's fine, but then the journal points the way only once the job is done.
- The Creator sometimes gives a move a name that doesn't quite match what it does once the forge has made it fair. One boss's "Summon Grave-Iron" ended up binding you in chains instead of summoning anything, which matched its description but not its name.
