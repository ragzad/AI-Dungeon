import streamlit as st
import json
from utils import load_game, save_game
from archivist import get_archivist_response, update_world_state
from narrator import narrate_scene
from illustrator import get_image_prompt

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
        # 1. Show Logic Logs (if they exist)
        if "debug_log" in message:
            with st.expander("🤖 Archivist Logic (Debug)"):
                st.json(message["debug_log"])
        
        # 2. Show Art (if it exists)
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
            missing_name = updates["target_name"]
            
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
                        # Add to inventory or world 
                        current_state["player"]["inventory"].append(new_entity["item_name"])
                        st.toast(f"✨ Created new Item: {missing_name}!")
                    
                    # --- CRITICAL FIX: SAVE TO DISK NOW ---
                    # We must save the new entity to the file BEFORE the Archivist runs again.
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
    
    # 6. Save everything to history
    st.session_state.messages.append({
        "role": "assistant", 
        "content": story,
        "art_prompt": art_prompt,
        "debug_log": updates  # <--- Saving the JSON here
    })
    
    st.rerun()