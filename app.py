import streamlit as st
import json
import base64
import urllib.parse
from utils import load_game, save_game
from archivist import get_archivist_response, update_world_state
from narrator import narrate_scene
from gtts import gTTS
from io import BytesIO
from director import update_story_state 
from creator import create_new_entity
from scribe import scan_story_for_entities

# --- CONSTANTS: DEFAULT STATE ---
DEFAULT_STATE = {
  "session_id": "new_game",
  "player": {
    "name": "Traveler",
    "hp": 20,
    "max_hp": 20,
    "inventory": []
  },
  "current_location_id": "loc_start",
  "world_flags": {
    "game_started": True
  },
  "locations": {
    "loc_start": {
      "name": "The Beginning",
      "description": "You stand in a gray void. To form the world, you must take an action. Will you draw a sword? Check your revolver? Or look at the stars?",
      "exits": ["forward"]
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

st.title("⚔️ The Dungeon Master")
st.markdown("*A Multi-Agent AI Roleplaying Engine*")

# --- SIDEBAR: WORLD STATE ---
st.sidebar.header("🛡️ Character Sheet")

# --- RESET BUTTON ---
if st.sidebar.button("🔄 Reset Game", type="primary"):
    save_game(DEFAULT_STATE)
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "The world is unformed. How do you begin?"
    })
    st.rerun()

current_state = load_game()

if current_state:
    player = current_state.get('player', {})
    
    # Stats
    st.sidebar.subheader(player.get('name', 'Unknown'))
    current_hp = player.get('hp', 0)
    max_hp = player.get('max_hp', 10)
    if max_hp > 0:
        bar_value = max(min(current_hp / max_hp, 1.0), 0.0)
        st.sidebar.progress(bar_value)
    st.sidebar.write(f"**HP:** {current_hp} / {max_hp}")
    
    # Inventory
    st.sidebar.subheader("🎒 Inventory")
    for item in player.get('inventory', []):
        st.sidebar.code(item)
    
    # Quest Log
    st.sidebar.subheader("📜 Current Story")
    story_data = current_state.get("story_state", {})
    st.sidebar.info(f"**Goal:** {story_data.get('current_objective', 'Explore')}")
    st.sidebar.write(f"**Genre:** {story_data.get('genre', 'Adaptive')}")
    with st.sidebar.expander("Director's Notes"):
        st.write(f"*{story_data.get('narrative_direction')}*")

    # Map
    st.sidebar.subheader("🗺️ World Map")
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
            st.sidebar.warning("Install 'graphviz' to see the map.")

    # Debug Flags
    with st.sidebar.expander("🌍 World Flags"):
        st.json(current_state.get('world_flags', {}))
    with st.sidebar.expander("👥 NPC Status"):
        st.json(current_state.get('npcs', {}))
    with st.sidebar.expander("🔥 Active Events"):
        st.json(current_state.get("world_events", []))

# --- CHAT LOGIC ---

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "The world is unformed. How do you begin?"
    })

# --- HISTORY LOOP ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "debug_log" in message:
            with st.expander("🤖 Archivist Logic (Debug)"):
                st.json(message["debug_log"])
        
        st.markdown(message["content"])

        if "audio_b64" in message and message["audio_b64"]:
            audio_html = f"""
                <audio controls style="width: 100%;">
                <source src="data:audio/mp3;base64,{message['audio_b64']}" type="audio/mp3">
                </audio>
            """
            st.markdown(audio_html, unsafe_allow_html=True)

# --- USER INPUT ---
if prompt := st.chat_input("What is your command?"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # --- 1. ARCHIVIST & CREATOR (Proactive Logic) ---
    with st.spinner("The Archivist is thinking..."):
        updates = get_archivist_response(current_state, prompt)
        
        if "error" in updates and updates["error"] == "target_missing":
            missing_name = updates.get("target_name", "Unknown Area")
            
            # Detect Vague Movement
            if missing_name.lower() in ["outside", "exit", "door", "leave", "out"]:
                missing_name = "The Surrounding Area" 
            
            with st.spinner(f"⚠️ Discovering '{missing_name}'..."):
                curr_loc = current_state.get("current_location_id", "unknown")
                
                # Call Creator directly (No shadow queue check)
                new_entity = create_new_entity(missing_name, curr_loc, current_state)
                
                if new_entity:
                    if new_entity["type"] == "location":
                        loc_id = new_entity["id"]
                        loc_data = new_entity["data"]
                        
                        # Fix Self-Looping Exits
                        clean_exits = [e for e in loc_data.get("exits", []) 
                                      if e.lower() != loc_data["name"].lower() 
                                      and "back to" not in e.lower()]
                        loc_data["exits"] = clean_exits
                        
                        if "locations" not in current_state: current_state["locations"] = {}
                        current_state["locations"][loc_id] = loc_data
                        
                        # Link Exits
                        old_loc_id = current_state["current_location_id"]
                        old_loc_name = current_state["locations"].get(old_loc_id, {}).get("name", "Previous Area")
                        loc_data["exits"].append(f"Back to {old_loc_name}")

                        if old_loc_id in current_state["locations"]:
                            if "exits" not in current_state["locations"][old_loc_id]:
                                current_state["locations"][old_loc_id]["exits"] = []
                            if loc_data["name"] not in current_state["locations"][old_loc_id]["exits"]:
                                current_state["locations"][old_loc_id]["exits"].append(loc_data["name"])

                        current_state["current_location_id"] = loc_id
                        
                        if "suggested_exits" in loc_data:
                            suggestions = "; ".join(loc_data["suggested_exits"])
                            updates["narrative_cue"] = f"You arrive at {loc_data['name']}. {loc_data['description']} Visible paths: {suggestions}."

                        st.toast(f"✨ Discovered: {loc_data['name']}")
                    
                    elif new_entity["type"] == "npc":
                         npc_id = new_entity["id"]
                         current_state["npcs"][npc_id] = new_entity["data"]
                         st.toast(f"✨ Met NPC: {new_entity['data']['name']}")

                    elif new_entity["type"] == "item":
                         current_state["player"]["inventory"].append(new_entity["item_name"])
                         updates["narrative_cue"] = f"You found a {new_entity['item_name']}."
                         st.toast(f"✨ Found Item: {new_entity['item_name']}")

                    save_game(current_state)
                    
                    if "narrative_cue" not in updates:
                        updates = get_archivist_response(current_state, prompt)
        
        log_msg = updates.get("narrative_cue", "Events unfold...")
        new_state = update_world_state(updates)

    # --- 2. THE DIRECTOR (Story Manager) ---
    with st.spinner("The Director is adapting the plot..."):
        director_output = update_story_state(new_state, prompt, log_msg)
        
        if "story_state" not in new_state: new_state["story_state"] = {}
        new_state["story_state"]["narrative_direction"] = director_output.get("narrative_direction")
        new_state["story_state"]["global_tension"] = director_output.get("global_tension", 1)
        
        if "world_events" in director_output:
            new_state["world_events"] = director_output["world_events"]
        
        save_game(new_state)

    # --- 3. NARRATOR ---
    with st.spinner("The Narrator is writing..."):
        story = narrate_scene(new_state, prompt, log_msg)

    # --- 4. THE SCRIBE (Sync) ---
    if story:
        new_entities = scan_story_for_entities(story, new_state)
        
        if "new_items" in new_entities and new_entities["new_items"]:
            for item in new_entities["new_items"]:
                new_state["player"]["inventory"].append(item)
                st.toast(f"📝 Scribe added item: {item}")
        
        if "new_npcs" in new_entities and new_entities["new_npcs"]:
            for npc in new_entities["new_npcs"]:
                nid = f"scribe_npc_{npc['name'].lower().replace(' ', '_')}"
                if nid not in new_state["npcs"]:
                    new_state["npcs"][nid] = {
                        "name": npc['name'],
                        "location_id": new_state["current_location_id"],
                        "status": npc.get("status", "alive"),
                        "attitude": "unknown",
                        "description": npc.get("description", "Noted by the Scribe.")
                    }
                    st.toast(f"📝 Scribe recorded NPC: {npc['name']}")

        if "new_locations" in new_entities and new_entities["new_locations"]:
            current_loc = new_state["locations"].get(new_state["current_location_id"])
            if current_loc:
                for loc in new_entities["new_locations"]:
                    lid = f"scribe_loc_{loc['name'].lower().replace(' ', '_')}"
                    if lid not in new_state["locations"]:
                        new_state["locations"][lid] = {
                            "name": loc['name'],
                            "description": loc.get("description", "Spotted in the distance."),
                            "exits": [f"Back to {current_loc['name']}"]
                        }
                        if "exits" not in current_loc: current_loc["exits"] = []
                        current_loc["exits"].append(loc['name'])
                        st.toast(f"📝 Scribe mapped: {loc['name']}")

        save_game(new_state)

    # --- 5. AUDIO GENERATION ---
    audio_b64 = None
    if story:
        try:
            tts = gTTS(text=story, lang='en', slow=False)
            audio_bytes = BytesIO()
            tts.write_to_fp(audio_bytes)
            audio_bytes.seek(0)
            audio_b64 = base64.b64encode(audio_bytes.read()).decode()
        except Exception as e:
            print(f"Audio Generation Error: {e}")

    # --- SAVE TO HISTORY ---
    st.session_state.messages.append({
        "role": "assistant", 
        "content": story,
        "audio_b64": audio_b64, 
        "debug_log": updates
    })
    
    st.rerun()