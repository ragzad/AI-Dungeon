import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# IMPORTS
from archivist import calculate_world_delta 
from creator import create_new_entity
from narrator import narrate_scene
from scribe import scan_story_for_entities
from cartographer import get_map_update

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def run_game_turn(current_state, player_input):
    debug_log = {}
    response_buffer = []
    
    # 1. CHECK FOR MOVEMENT
    map_data = get_map_update(current_state, player_input)
    debug_log["map_data"] = map_data
    
    if map_data.get("is_movement"):
        dest_name = map_data["destination_name"]
        
        # Check if location exists
        dest_id = None
        for lid, loc in current_state["locations"].items():
            if loc["name"].lower() == dest_name.lower():
                dest_id = lid
                break
        
        # Create if new
        if not dest_id:
            debug_log["action"] = f"Discovering {dest_name}"
            new_loc = create_new_entity(dest_name, current_state.get("current_location_id"), current_state)
            if new_loc and new_loc["type"] == "location":
                dest_id = new_loc["id"]
                current_state["locations"][dest_id] = new_loc["data"]
                
                # Link exits
                prev_id = current_state["current_location_id"]
                prev_loc = current_state["locations"].get(prev_id)
                if prev_loc:
                    if "exits" not in prev_loc: prev_loc["exits"] = []
                    if dest_name not in prev_loc["exits"]: prev_loc["exits"].append(dest_name)
                    if "exits" not in new_loc["data"]: new_loc["data"]["exits"] = []
                    new_loc["data"]["exits"].append(prev_loc["name"])

        if dest_id:
            current_state["current_location_id"] = dest_id
            response_buffer.append(f"**Travel:** You head towards {dest_name}...")
            
            # --- PROACTIVE POPULATION (MAKE IT ALIVE) ---
            loc_data = current_state["locations"][dest_id]
            
            # If no items, spawn some ambiance
            if not loc_data.get("items"):
                if "items" not in loc_data: loc_data["items"] = []
                flavor_item = create_new_entity(f"Common items found in {dest_name}", dest_id, current_state)
                if flavor_item and flavor_item["type"] == "item":
                    loc_data["items"].append({
                        "name": flavor_item["item_name"], 
                        "state": "ground", 
                        "description": "Part of the scene."
                    })
            
            # If no NPCs, spawn a local
            # We assume a 50% chance for a random NPC in a new area to make it feel inhabited
            # (In a real game, you might want more complex logic here)
            local_npcs = [n for n in current_state["npcs"].values() if n["location_id"] == dest_id]
            if not local_npcs:
                 flavor_npc = create_new_entity(f"A typical inhabitant of {dest_name}", dest_id, current_state)
                 if flavor_npc and flavor_npc["type"] == "npc":
                     current_state["npcs"][flavor_npc["id"]] = flavor_npc["data"]

    # 2. RUN ARCHIVIST
    delta = calculate_world_delta(current_state, player_input)
    debug_log["engine_delta"] = delta
    
    # 3. APPLY DELTA (State Update)
    p_delta = delta.get("player_delta", {})
    current_state["player"]["hp"] += p_delta.get("hp_change", 0)
    
    # --- CRITICAL FIX: Handle Strings vs Objects for Inventory ---
    for item in p_delta.get("inventory_add", []):
        if isinstance(item, str):
            current_state["player"]["inventory"].append({"name": item, "description": "Acquired item.", "state": "normal"})
        else:
            current_state["player"]["inventory"].append(item)
        
    if p_delta.get("inventory_remove"):
        rem_names = [n.lower() for n in p_delta.get("inventory_remove")]
        current_state["player"]["inventory"] = [
            i for i in current_state["player"]["inventory"] 
            if (i.get("name") if isinstance(i, dict) else str(i)).lower() not in rem_names
        ]

    l_delta = delta.get("location_delta", {})
    current_loc = current_state["locations"][current_state["current_location_id"]]
    
    # --- CRITICAL FIX: Handle Strings vs Objects for Ground Items ---
    if l_delta.get("ground_items_add"):
        if "items" not in current_loc: current_loc["items"] = []
        for i in l_delta["ground_items_add"]: 
            if isinstance(i, str):
                current_loc["items"].append({"name": i, "description": "On the ground.", "state": "ground"})
            else:
                current_loc["items"].append(i)
        
    if l_delta.get("ground_items_remove"):
        rem_ground = [n.lower() for n in l_delta["ground_items_remove"]]
        current_loc["items"] = [
            i for i in current_loc.get("items", []) 
            if (i.get("name") if isinstance(i, dict) else str(i)).lower() not in rem_ground
        ]

    q_delta = delta.get("quest_update", {})
    if q_delta.get("new_objective"):
        current_state["story_state"]["current_objective"] = q_delta["new_objective"]

    # 4. RENDER STORY
    story = narrate_scene(current_state, player_input, delta)
    response_buffer.append(story)
    
    # 5. SCRIBE (Sync)
    new_entities = scan_story_for_entities(story, current_state)
    
    if "new_items" in new_entities and new_entities["new_items"]:
        for item_name in new_entities["new_items"]:
             current_state["player"]["inventory"].append({
                    "name": item_name, "description": "Obtained.", "state": "acquired"
             })
    
    if "new_npcs" in new_entities and new_entities["new_npcs"]:
        for npc in new_entities["new_npcs"]:
            if npc.get("presence") == "physical":
                nid = f"scribe_npc_{npc['name'].lower().replace(' ', '_')}"
                if nid not in current_state["npcs"]:
                    current_state["npcs"][nid] = {
                        "name": npc['name'],
                        "location_id": current_state["current_location_id"],
                        "status": npc.get("status", "alive"),
                        "attitude": "unknown",
                        "description": npc.get("description", "Noted by the Scribe.")
                    }
    
    if "new_lore" in new_entities and new_entities["new_lore"]:
        if "journal" not in current_state["player"]: current_state["player"]["journal"] = []
        for entry in new_entities["new_lore"]:
            if not any(e['topic'] == entry['topic'] for e in current_state["player"]["journal"]):
                current_state["player"]["journal"].append(entry)

    final_response = "\n\n".join(response_buffer)
    return {"response": final_response, "state": current_state, "debug_log": debug_log}