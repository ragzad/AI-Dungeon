import streamlit as st
import json
import base64
from utils import load_game, save_game
from archivist import get_archivist_response, update_world_state
from narrator import narrate_scene
from gtts import gTTS
from io import BytesIO
from director import update_story_state 
from creator import create_new_entity, generate_full_scenario, generate_random_scenario_idea
from scribe import scan_story_for_entities

# --- CONSTANTS: DEFAULT STATE ---
DEFAULT_STATE = {
  "session_id": "new_game",
  "player": {
    "name": "Traveler",
    "hp": 20,
    "max_hp": 20,
    "inventory": [
        {"name": "Old Map", "description": "A faded, brittle map fragment.", "state": "default"},
        {"name": "Dagger", "description": "A simple iron blade.", "state": "dull"}
    ],
    "journal": [] # NEW: Stores Lore/Clues
  },
  "current_location_id": "loc_start",
  "world_flags": {
    "game_started": False 
  },
  "locations": {
    "loc_start": {
      "name": "The Void",
      "description": "The unformed nothingness before creation.",
      "exits": []
    }
  },
  "npcs": {},
  "story_state": {
    "current_act": 1,
    "global_tension": 1,
    "genre": "adaptive",
    "current_objective": "Establish the setting.",
    "narrative_direction": "Observe the player's tone to determine the genre."
  },
  "world_events": []
}

# --- UI CONFIGURATION ---
st.set_page_config(page_title="The Dungeon Master", layout="wide")

# --- INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []

if "scenario_input" not in st.session_state:
    st.session_state["scenario_input"] = ""

current_state = load_game()
if not current_state:
    current_state = DEFAULT_STATE
    save_game(current_state)

# ==========================================
#  GENESIS MODE
# ==========================================
if not current_state.get("world_flags", {}).get("game_started", False):
    st.title("⚔️ Create Your World")
    st.markdown("Before we begin, tell the Dungeon Master what kind of story you want to play.")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        st.info("Or let fate decide...")
        if st.button("🎲 Surprise Me", use_container_width=True):
            with st.spinner("Dreaming up a nightmare..."):
                random_idea = generate_random_scenario_idea()
                st.session_state["scenario_input"] = random_idea
            st.rerun()

    with col1:
        scenario_prompt = st.text_area("Scenario / Theme", 
            key="scenario_input",
            placeholder="e.g., A gritty noir detective story on Mars...",
            height=150)
    
    if st.button("🚀 Launch Adventure", type="primary", use_container_width=True):
        if not scenario_prompt:
            st.warning("Please enter a prompt.")
        else:
            with st.spinner("The World Architect is building your reality..."):
                scenario_data = generate_full_scenario(scenario_prompt)
                if scenario_data:
                    start_id = "loc_genesis_start" 
                    new_state = {
                        "session_id": "custom_game",
                        "player": {
                            "name": scenario_data["player"]["name"],
                            "hp": 20, "max_hp": 20,
                            "inventory": scenario_data["player"]["inventory"],
                            "journal": [] # Ensure Journal is initialized
                        },
                        "current_location_id": start_id,
                        "world_flags": {"game_started": True},
                        "locations": {
                            start_id: scenario_data["location"]
                        },
                        "npcs": {},
                        "story_state": {
                            "current_act": 1,
                            "global_tension": 1,
                            "genre": scenario_data["genre"],
                            "current_objective": "Survive and explore.",
                            "narrative_direction": "Begin the adventure."
                        },
                        "world_events": []
                    }
                    save_game(new_state)
                    st.session_state.messages = [{"role": "assistant", "content": scenario_data["intro_text"]}]
                    st.rerun()
                else:
                    st.error("Generation Failed.")

# ==========================================
#  GAME MODE
# ==========================================
else:
    st.title(f"⚔️ {current_state['story_state'].get('genre', 'Adventure').title()}")

    # --- SIDEBAR ---
    st.sidebar.header("🛡️ Character Sheet")
    if st.sidebar.button("🔄 New Adventure", type="primary"):
        save_game(DEFAULT_STATE)
        st.session_state.messages = []
        st.session_state["scenario_input"] = ""
        st.rerun()

    player = current_state.get('player', {})
    
    # HP
    st.sidebar.subheader(player.get('name', 'Unknown'))
    current_hp = player.get('hp', 0)
    max_hp = player.get('max_hp', 10)
    if max_hp > 0:
        bar_value = max(min(current_hp / max_hp, 1.0), 0.0)
        st.sidebar.progress(bar_value)
    
    # Inventory
    st.sidebar.subheader("🎒 Inventory")
    inventory = player.get('inventory', [])
    if inventory:
        for item in inventory:
            if isinstance(item, dict):
                with st.sidebar.expander(f"🔹 {item['name']}"):
                    st.caption(item.get('description', 'No description.'))
                    st.caption(f"*State: {item.get('state', 'normal')}*")
            else:
                st.sidebar.code(str(item))
    else:
        st.sidebar.caption("Empty.")

    # Story Info
    st.sidebar.divider()
    st.sidebar.subheader("📜 Quest")
    story_data = current_state.get("story_state", {})
    st.sidebar.info(f"**Goal:** {story_data.get('current_objective', 'Explore')}")
    st.sidebar.caption(f"**Tension:** {story_data.get('global_tension', 1)}/10")
    
    # DM Tools / Database
    st.sidebar.divider()
    with st.sidebar.expander("🌍 World Database", expanded=False):
        tab_npcs, tab_events, tab_journal = st.tabs(["👥 NPCs", "🔥 Events", "📖 Journal"])
        
        with tab_npcs:
            npcs = current_state.get('npcs', {})
            if npcs:
                npc_list = []
                for nid, data in npcs.items():
                    npc_list.append({"Name": data.get("name"), "Attitude": data.get("attitude")})
                st.dataframe(npc_list, hide_index=True)
            else:
                st.caption("No NPCs met.")

        with tab_events:
            events = current_state.get("world_events", [])
            if events:
                event_display = [{"Name": e["name"], "Status": e.get("status")} for e in events]
                st.dataframe(event_display, hide_index=True)
            else:
                st.caption("No active events.")

        with tab_journal:
            journal = player.get("journal", [])
            if journal:
                for entry in journal:
                    st.markdown(f"**{entry['topic']}**")
                    st.caption(entry['entry'])
                    st.divider()
            else:
                st.caption("No lore discovered.")

    # Map
    st.sidebar.subheader("🗺️ Map")
    if "locations" in current_state:
        try:
            import graphviz
            graph = graphviz.Digraph()
            graph.attr(rankdir='LR', size='10', bgcolor='transparent')
            for loc_id, loc_data in current_state["locations"].items():
                if loc_id == current_state.get("current_location_id"):
                    graph.node(loc_id, label=loc_data["name"], style='filled', fillcolor='#ffcccc', shape='box')
                else:
                    graph.node(loc_id, label=loc_data["name"], shape='ellipse', style='filled', fillcolor='#f0f2f6')
            st.sidebar.graphviz_chart(graph)
        except ImportError:
            pass

    # --- CHAT ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "debug_log" in message:
                with st.expander("🤖 Archivist Logic"):
                    st.json(message["debug_log"])
            st.markdown(message["content"])
            if "audio_b64" in message and message["audio_b64"]:
                audio_html = f"""
                    <audio controls style="width: 100%;">
                    <source src="data:audio/mp3;base64,{message['audio_b64']}" type="audio/mp3">
                    </audio>
                """
                st.markdown(audio_html, unsafe_allow_html=True)

    # --- INPUT ---
    if prompt := st.chat_input("What do you do?"):
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # 1. ARCHIVIST
        with st.spinner("The Archivist is thinking..."):
            updates = get_archivist_response(current_state, prompt)
            
            # Creator Logic (Discovery)
            if "error" in updates and updates["error"] == "target_missing":
                missing_name = updates.get("target_name", "Unknown Area")
                if missing_name.lower() in ["outside", "exit", "door", "leave", "out"]:
                    missing_name = "The Surrounding Area" 
                with st.spinner(f"⚠️ Discovering '{missing_name}'..."):
                    curr_loc = current_state.get("current_location_id", "unknown")
                    new_entity = create_new_entity(missing_name, curr_loc, current_state)
                    if new_entity:
                        if new_entity["type"] == "location":
                            loc_id = new_entity["id"]
                            loc_data = new_entity["data"]
                            clean_exits = [e for e in loc_data.get("exits", []) if e.lower() != loc_data["name"].lower()]
                            loc_data["exits"] = clean_exits
                            current_state["locations"][loc_id] = loc_data
                            
                            old_loc_id = current_state["current_location_id"]
                            old_loc = current_state["locations"].get(old_loc_id)
                            if old_loc:
                                if "exits" not in old_loc: old_loc["exits"] = []
                                if loc_data["name"] not in old_loc["exits"]:
                                    old_loc["exits"].append(loc_data["name"])
                                loc_data["exits"].append(f"Back to {old_loc['name']}")
                            
                            current_state["current_location_id"] = loc_id
                            if "suggested_exits" in loc_data:
                                suggestions = "; ".join(loc_data["suggested_exits"])
                                updates["narrative_cue"] = f"You arrive at {loc_data['name']}. {loc_data['description']} Visible paths: {suggestions}."
                            st.toast(f"✨ Discovered: {loc_data['name']}")
                        
                        elif new_entity["type"] == "npc":
                             current_state["npcs"][new_entity["id"]] = new_entity["data"]
                             st.toast(f"✨ Met NPC: {new_entity['data']['name']}")
                        
                        elif new_entity["type"] == "item":
                             item_obj = {"name": new_entity["item_name"], "description": "Discovered.", "state": "found"}
                             current_state["player"]["inventory"].append(item_obj)
                             updates["narrative_cue"] = f"You found a {new_entity['item_name']}."
                             st.toast(f"✨ Found Item: {new_entity['item_name']}")
                        
                        save_game(current_state)
                        if "narrative_cue" not in updates:
                            updates = get_archivist_response(current_state, prompt)
            
            log_msg = updates.get("narrative_cue", "Events unfold...")
            new_state = update_world_state(updates)

        # 2. DIRECTOR
        with st.spinner("The Director is adapting the plot..."):
            director_output = update_story_state(new_state, prompt, log_msg)
            if "story_state" not in new_state: new_state["story_state"] = {}
            new_state["story_state"]["narrative_direction"] = director_output.get("narrative_direction")
            new_state["story_state"]["global_tension"] = director_output.get("global_tension", 1)
            if "current_objective" in director_output:
                new_state["story_state"]["current_objective"] = director_output["current_objective"]
            if "world_events" in director_output:
                new_state["world_events"] = director_output["world_events"]
            save_game(new_state)

        # 3. NARRATOR
        with st.spinner("The Narrator is writing..."):
            story = narrate_scene(new_state, prompt, log_msg)

        # 4. SCRIBE (Sync)
        if story:
            new_entities = scan_story_for_entities(story, new_state)
            
            # Items
            if "new_items" in new_entities and new_entities["new_items"]:
                for item_name in new_entities["new_items"]:
                    existing_names = [i["name"].lower() if isinstance(i, dict) else str(i).lower() for i in new_state["player"]["inventory"]]
                    if item_name.lower() not in existing_names:
                        new_state["player"]["inventory"].append({"name": item_name, "description": "Added by Scribe.", "state": "acquired"})
                        st.toast(f"📝 Scribe added item: {item_name}")
            
            # NPCs
            if "new_npcs" in new_entities and new_entities["new_npcs"]:
                for npc in new_entities["new_npcs"]:
                    if npc.get("presence") == "physical":
                        nid = f"scribe_npc_{npc['name'].lower().replace(' ', '_')}"
                        if nid not in new_state["npcs"]:
                            new_state["npcs"][nid] = {
                                "name": npc['name'], 
                                "location_id": new_state["current_location_id"], 
                                "status": npc.get("status", "alive"), 
                                "attitude": "unknown"
                            }
                            st.toast(f"📝 Scribe recorded NPC: {npc['name']}")

            # Locations
            if "new_locations" in new_entities and new_entities["new_locations"]:
                for loc in new_entities["new_locations"]:
                    lid = f"scribe_loc_{loc['name'].lower().replace(' ', '_')}"
                    if lid not in new_state["locations"]:
                        new_state["locations"][lid] = {"name": loc['name'], "description": loc.get("description", "A location."), "exits": []}
                        curr_id = new_state.get("current_location_id")
                        if curr_id in new_state["locations"]:
                            if loc["name"] not in new_state["locations"][curr_id]["exits"]:
                                new_state["locations"][curr_id]["exits"].append(loc["name"])
                        st.toast(f"📝 Scribe mapped: {loc['name']}")
            
            # --- NEW: JOURNAL LOGIC ---
            if "new_lore" in new_entities and new_entities["new_lore"]:
                if "journal" not in new_state["player"]:
                    new_state["player"]["journal"] = []
                for entry in new_entities["new_lore"]:
                    # Check for duplicates (simple check)
                    is_dupe = any(e['topic'] == entry['topic'] for e in new_state["player"]["journal"])
                    if not is_dupe:
                        new_state["player"]["journal"].append(entry)
                        st.toast(f"📖 Journal Updated: {entry['topic']}")

            save_game(new_state)

        # 5. AUDIO
        audio_b64 = None
        if story:
            try:
                tts = gTTS(text=story, lang='en', slow=False)
                audio_bytes = BytesIO()
                tts.write_to_fp(audio_bytes)
                audio_bytes.seek(0)
                audio_b64 = base64.b64encode(audio_bytes.read()).decode()
            except Exception:
                pass

        st.session_state.messages.append({
            "role": "assistant", 
            "content": story,
            "audio_b64": audio_b64, 
            "debug_log": updates
        })
        st.rerun()