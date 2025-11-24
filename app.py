import streamlit as st
import json
from utils import load_game, save_game
from archivist import get_archivist_response, update_world_state
from narrator import narrate_scene
from illustrator import get_image_prompt
import base64

# --- UI CONFIGURATION ---
st.set_page_config(page_title="The Dungeon Master", layout="wide")

st.title("⚔️ The Dungeon Master")
st.markdown("*A Multi-Agent AI Roleplaying Engine*")

# --- SIDEBAR: WORLD STATE (The "Memory") ---
st.sidebar.header("🛡️ Character Sheet")

current_state = load_game()

if current_state:
    player = current_state['player']
    
    # Display Stats
    st.sidebar.subheader(player['name'])
    current_hp = player['hp']
    max_hp = player['max_hp']
    # Safety check to keep progress bar between 0.0 and 1.0
    bar_value = max(min(current_hp / max_hp, 1.0), 0.0)
    
    st.sidebar.progress(bar_value)
    st.sidebar.write(f"**HP:** {current_hp} / {max_hp}")
    
    # Display Inventory
    st.sidebar.subheader("🎒 Inventory")
    for item in player['inventory']:
        st.sidebar.code(item)
    
    # --- PHASE 2: THE CARTOGRAPHER (Dynamic Map) ---
    st.sidebar.subheader("🗺️ World Map")
    if "locations" in current_state:
        try:
            import graphviz
            graph = graphviz.Digraph()
            graph.attr(rankdir='LR', size='10', bgcolor='transparent')
            
            # Loop through all known locations
            for loc_id, loc_data in current_state["locations"].items():
                # Color the current location RED
                if loc_id == current_state.get("current_location_id"):
                    graph.node(loc_id, label=loc_data["name"], style='filled', fillcolor='#ffcccc', shape='box')
                else:
                    graph.node(loc_id, label=loc_data["name"], shape='ellipse', style='filled', fillcolor='#f0f2f6')
            
            st.sidebar.graphviz_chart(graph)
        except ImportError:
            st.sidebar.warning("Install 'graphviz' to see the map.")
    # -----------------------------------------------

    # Display World Flags
    with st.sidebar.expander("🌍 World Flags"):
        st.sidebar.json(current_state['world_flags'])
        
    with st.sidebar.expander("👥 NPC Status"):
        st.sidebar.json(current_state['npcs'])

# --- CHAT LOGIC ---

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "You stand in the dim light of the tavern. The air smells of stale ale. What do you do?"
    })

# --- HISTORY LOOP ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # 1. Show Logic Logs
        if "debug_log" in message:
            with st.expander("🤖 Archivist Logic (Debug)"):
                st.json(message["debug_log"])
        
        # 2. Show Art
        if "art_prompt" in message and message["art_prompt"]:
            with st.expander("🎨 Illustrator's Vision"):
                st.write(f"*{message['art_prompt']}*")
                st.image("https://placehold.co/600x300/222/FFF?text=Visual+Imagination+Active", caption="Scene Visualization Placeholder")
        
        # 3. Show Story
        st.markdown(message["content"])

# --- USER INPUT ---
if prompt := st.chat_input("What is your command?"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. THE ARCHIVIST (Logic) with Creator Fallback
    with st.spinner("The Archivist is thinking..."):
        updates = get_archivist_response(current_state, prompt)
        
        # CHECK: Did the Archivist fail to find the target?
        if "error" in updates and updates["error"] == "target_missing":
            # --- FIX: DEFENSIVE CODING ---
            # If the AI forgets 'target_name', guess it from the prompt or use a placeholder
            missing_name = updates.get("target_name", "Unknown Entity")
            # -----------------------------
            
            # TRIGGER THE CREATOR
            with st.spinner(f"⚠️ Entity '{missing_name}' not found. Spawning it now..."):
                from creator import create_new_entity
                
                # Assume location is the player's current location (or default)
                curr_loc = current_state.get("current_location_id", "unknown")
                new_entity = create_new_entity(missing_name, curr_loc)
                
                if new_entity:
                    # Inject into State immediately (In Memory)
                    if new_entity["type"] == "npc":
                        npc_id = new_entity["id"]
                        current_state["npcs"][npc_id] = new_entity["data"]
                        st.toast(f"✨ Created new NPC: {missing_name}!")
                        
                    elif new_entity["type"] == "item":
                        current_state["player"]["inventory"].append(new_entity["item_name"])
                        st.toast(f"✨ Created new Item: {missing_name}!")

                    # --- PHASE 1: THE WORLD FORGER (Location Gen) ---
                    elif new_entity["type"] == "location":
                        loc_id = new_entity["id"]
                        # Ensure locations dict exists
                        if "locations" not in current_state:
                            current_state["locations"] = {}
                        
                        # Add new location
                        current_state["locations"][loc_id] = new_entity["data"]
                        # Teleport Player
                        current_state["current_location_id"] = loc_id
                        
                        st.toast(f"✨ Discovered new Area: {missing_name}!")
                    # ------------------------------------------------
                    
                    # --- CRITICAL FIX: SAVE TO DISK NOW ---
                    save_game(current_state)
                    # --------------------------------------
                    
                    # RETRY the original action with the new state
                    updates = get_archivist_response(current_state, prompt)
        
        # Proceed as normal
        log_msg = updates.get("narrative_cue", "Events unfold...")
        new_state = update_world_state(updates)

    # 3. THE NARRATOR (Story)
    with st.spinner("The Narrator is writing..."):
        story = narrate_scene(new_state, prompt, log_msg)

    # 4. THE ILLUSTRATOR (Visuals)
    with st.spinner("The Illustrator is sketching..."):
        art_prompt = get_image_prompt(story)
        
    # 5. Display Result
    with st.chat_message("assistant"):
        # SHOW THE LOGIC!
        with st.expander("🤖 Archivist Logic (Debug)"):
            st.json(updates)
            
        with st.expander("🎨 Illustrator's Vision"):
            st.write(f"*{art_prompt}*")
            st.image("https://placehold.co/600x300/222/FFF?text=Visual+Imagination+Active", caption="Scene Visualization Placeholder")
            
        st.markdown(story)

# --- PHASE 3: THE BARD (Audio - CRASH PROOF VERSION) ---
        try:
            from gtts import gTTS
            from io import BytesIO 
            
            if story:
                # 1. Generate Audio into Memory
                tts = gTTS(text=story, lang='en')
                audio_bytes = BytesIO()
                tts.write_to_fp(audio_bytes)
                audio_bytes.seek(0)
                
                # 2. Convert to Base64 (Embeds it directly in HTML)
                b64 = base64.b64encode(audio_bytes.read()).decode()
                
                # 3. Render HTML Audio Player
                audio_html = f"""
                    <audio controls autoplay>
                    <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                    </audio>
                """
                st.markdown(audio_html, unsafe_allow_html=True)
                
        except Exception as e:
            # If audio fails, we log it but DO NOT CRASH the app
            print(f"Audio Error: {e}")
        # ---------------------------------
    
    # 6. Save everything to history
    st.session_state.messages.append({
        "role": "assistant", 
        "content": story,
        "art_prompt": art_prompt,
        "debug_log": updates
    })
    
    st.rerun()