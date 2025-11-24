import streamlit as st
import json
from utils import load_game
from archivist import get_archivist_response, update_world_state
from narrator import narrate_scene
from illustrator import get_image_prompt

# --- UI CONFIGURATION ---
st.set_page_config(page_title="The Dungeon Master", layout="wide")

st.title("⚔️ The Dungeon Master")
st.markdown("*A Multi-Agent AI Roleplaying Engine*")

# --- SIDEBAR: WORLD STATE (The "Memory") ---
st.sidebar.header("🛡️ Character Sheet")

# Load state fresh every reload to ensure sync
current_state = load_game()

if current_state:
    player = current_state['player']
    
    # Display Stats
    st.sidebar.subheader(player['name'])
    
    # --- FIX: Calculate safe progress value ---
    current_hp = player['hp']
    max_hp = player['max_hp']
    
    # Ensure value is never greater than 1.0, even if HP > Max HP
    bar_value = min(current_hp / max_hp, 1.0)
    # Ensure value is never less than 0.0
    bar_value = max(bar_value, 0.0)
    
    st.sidebar.progress(bar_value)
    st.sidebar.write(f"**HP:** {current_hp} / {max_hp}")
    
    # Display Inventory
    st.sidebar.subheader("🎒 Inventory")
    for item in player['inventory']:
        st.sidebar.code(item)
    
    # Display World Flags (Debug View)
    with st.sidebar.expander("🌍 World Flags (Debug)"):
        st.sidebar.json(current_state['world_flags'])
        
    with st.sidebar.expander("👥 NPC Status (Debug)"):
        st.sidebar.json(current_state['npcs'])

# --- CHAT LOGIC ---

# Initialize chat history if it doesn't exist
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Add an intro message
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "You stand in the dim light of the tavern. The air smells of stale ale. What do you do?"
    })

# --- FIXED HISTORY LOOP ---
# We now check if there is 'art_prompt' data saved in the message
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # If this message has an art prompt, show the expander
        if "art_prompt" in message and message["art_prompt"]:
            with st.expander("🎨 Illustrator's Vision"):
                st.write(f"*{message['art_prompt']}*")
                st.image("https://placehold.co/600x300/222/FFF?text=Visual+Imagination+Active", caption="Scene Visualization Placeholder")
        
        # Then show the story text
        st.markdown(message["content"])

# --- USER INPUT ---
if prompt := st.chat_input("What is your command?"):
    # 1. Display User Message
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. THE ARCHIVIST (Logic)
    with st.spinner("The Archivist is updating the world..."):
        updates = get_archivist_response(current_state, prompt)
        log_msg = updates.get("narrative_cue", "Events unfold...")
        
        # Apply updates to the JSON file
        new_state = update_world_state(updates)

    # 3. THE NARRATOR (Story)
    with st.spinner("The Narrator is writing..."):
        story = narrate_scene(new_state, prompt, log_msg)

    # 4. THE ILLUSTRATOR (Visuals)
    with st.spinner("The Illustrator is sketching..."):
        art_prompt = get_image_prompt(story)
        
    # 5. Display Assistant Message (Ephemeral for this run)
    with st.chat_message("assistant"):
        with st.expander("🎨 Illustrator's Vision"):
            st.write(f"*{art_prompt}*")
            st.image("https://placehold.co/600x300/222/FFF?text=Visual+Imagination+Active", caption="Scene Visualization Placeholder")
            
        st.markdown(story)
    
    # 6. SAVE TO HISTORY (FIXED)
    # We now save the 'art_prompt' into the session state so it persists after rerun
    st.session_state.messages.append({
        "role": "assistant", 
        "content": story,
        "art_prompt": art_prompt 
    })
    
    # 7. Rerun to update Sidebar immediately
    st.rerun()