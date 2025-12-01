import streamlit as st
import json
import base64
from utils import load_game, save_game
from creator import generate_full_scenario, generate_random_scenario_idea
from gamemaster import run_game_turn
from cartographer import render_map 

# NEW VOICE ENGINE
from voice import generate_voice_audio

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
    "journal": [] 
  },
  "current_location_id": "loc_start",
  "world_flags": { "game_started": False },
  "locations": {
    "loc_start": {
      "name": "The Void",
      "description": "Unformed nothingness.",
      "exits": [],
      "items": [] 
    }
  },
  "npcs": {},
  "story_state": {
    "current_act": 1,
    "global_tension": 1,
    "genre": "adaptive",
    "current_objective": "Begin.",
    "narrative_direction": "Start."
  },
  "world_events": []
}

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
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🎲 Surprise Me", use_container_width=True):
            with st.spinner("Dreaming..."):
                st.session_state["scenario_input"] = generate_random_scenario_idea()
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
            with st.spinner("Building Reality..."):
                scenario_data = generate_full_scenario(scenario_prompt)
                if scenario_data:
                    start_id = "loc_genesis_start"
                    new_state = DEFAULT_STATE.copy()
                    
                    new_state["player"]["name"] = scenario_data["player"]["name"]
                    new_state["player"]["inventory"] = scenario_data["player"]["inventory"]
                    
                    loc_data = scenario_data["location"]
                    if "items" not in loc_data: loc_data["items"] = []
                    
                    new_state["locations"] = { start_id: loc_data }
                    new_state["current_location_id"] = start_id
                    new_state["world_flags"]["game_started"] = True
                    new_state["story_state"]["genre"] = scenario_data["genre"]
                    
                    save_game(new_state)
                    
                    # Generate Intro Audio
                    intro_text = scenario_data["intro_text"]
                    audio_b64 = generate_voice_audio(intro_text)
                    
                    st.session_state.messages = [{
                        "role": "assistant", 
                        "content": intro_text,
                        "audio_b64": audio_b64
                    }]
                    st.rerun()
                else:
                    st.error("Generation Failed. Try again.")

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
    
    st.sidebar.subheader(player.get('name', 'Unknown'))
    current_hp = player.get('hp', 0)
    max_hp = player.get('max_hp', 10)
    if max_hp > 0:
        bar_value = max(min(current_hp / max_hp, 1.0), 0.0)
        st.sidebar.progress(bar_value)
    
    st.sidebar.subheader("🎒 Inventory")
    inventory = player.get('inventory', [])
    if inventory:
        for item in inventory:
            if isinstance(item, dict):
                with st.sidebar.expander(f"🔹 {item.get('name', 'Unknown')}"):
                    st.caption(item.get('description', 'No description.'))
                    st.caption(f"*State: {item.get('state', 'normal')}*")
            else:
                st.sidebar.code(str(item))
    else:
        st.sidebar.caption("Empty.")

    st.sidebar.subheader("📍 Nearby Items")
    current_loc_id = current_state.get("current_location_id")
    loc_items = current_state.get("locations", {}).get(current_loc_id, {}).get("items", [])
    if loc_items:
        for item in loc_items:
             if isinstance(item, dict):
                 st.sidebar.caption(f"▫️ {item.get('name', 'Unknown')}")
             else:
                 st.sidebar.caption(f"▫️ {str(item)}")
    else:
        st.sidebar.caption("Nothing visible on the ground.")

    st.sidebar.divider()
    st.sidebar.subheader("📜 Quest")
    story_data = current_state.get("story_state", {})
    st.sidebar.info(f"**Goal:** {story_data.get('current_objective', 'Explore')}")
    st.sidebar.caption(f"**Tension:** {story_data.get('global_tension', 1)}/10")
    
    st.sidebar.divider()
    if "locations" in current_state:
        with st.sidebar.expander("🗺️ World Map", expanded=False):
            try:
                graph = render_map(current_state)
                st.graphviz_chart(graph)
            except ImportError:
                st.sidebar.caption("Graphviz not installed.")

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
                    st.markdown(f"**{entry.get('topic', 'Unknown')}**")
                    st.caption(entry.get('entry', ''))
                    st.divider()
            else:
                st.caption("No lore discovered.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "debug_log" in message:
                with st.expander("🤖 GM Logic"):
                    st.json(message["debug_log"])
            st.markdown(message["content"])
            
            # --- AUDIO PLAYER (PCM to WAV conversion handled by browser/API) ---
            if "audio_b64" in message and message["audio_b64"]:
                # Note: Gemini TTS returns PCM16 usually, but for simplicity here we assume
                # the browser can handle the base64 or we wrap it.
                # If using the standard Vertex/Gemini REST API as in voice.py, 
                # we are getting raw audio content.
                audio_html = f"""
                    <audio controls style="width: 100%;">
                    <source src="data:audio/wav;base64,{message['audio_b64']}" type="audio/wav">
                    </audio>
                """
                st.markdown(audio_html, unsafe_allow_html=True)

    if prompt := st.chat_input("What do you do?"):
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.spinner("The Game Master is orchestrating..."):
            result = run_game_turn(current_state, prompt)
            response_text = result["response"]
            new_state = result["state"]
            debug_log = result["debug_log"]

            old_obj = current_state["story_state"].get("current_objective")
            new_obj = new_state["story_state"].get("current_objective")
            if old_obj != new_obj:
                st.toast(f"📜 Quest Updated: {new_obj}", icon="⚔️")
            
            delta = debug_log.get("engine_delta", {}).get("player_delta", {})
            if delta and delta.get("inventory_add"):
                for i in delta["inventory_add"]:
                    name = i['name'] if isinstance(i, dict) else str(i)
                    st.toast(f"🎒 Acquired: {name}", icon="✨")

            # --- NEW VOICE GENERATION ---
            audio_b64 = generate_voice_audio(response_text)
            
            save_game(new_state)

        st.session_state.messages.append({
            "role": "assistant", 
            "content": response_text,
            "audio_b64": audio_b64,
            "debug_log": debug_log
        })
        st.rerun()