# AI Dungeon Master

AI Dungeon Master is an immersive, infinite text-adventure engine powered by Google's Gemini Pro. Unlike standard "chat with an AI" games, this project uses a multi-agent architecture to track inventory, quests, locations, and lore consistently.

## Features

* **Dynamic World Generation**: Start with a simple prompt (e.g., "Cyberpunk detective on Mars") and the AI builds a starting location, player stats, and intro.
* **Consistent Game State**: A structured JSON database tracks HP, Inventory, NPCs, and World Events. The AI cannot "forget" you have a sword.
* **Visual Map Mapping**: The Cartographer agent automatically detects movement and draws a graph of the world as you explore (requires Graphviz).
* **Smart Inventory & Loot**: The system recognizes when you pick up items and adds them to your structured inventory.
* **Lore Tracking**: A Scribe agent scans the story for new facts and updates your in-game journal automatically.

## Architecture

The project is split into several specialized "Agents" (Python modules) that handle different aspects of the simulation:

| Agent / Module | Responsibility |
| :--- | :--- |
| **app.py** | The frontend interface (Streamlit). Handles UI and state persistence. |
| **gamemaster.py** | The central orchestrator. It receives user input and calls the other agents in order. |
| **archivist.py** | The "Logic Engine". It calculates HP changes, inventory updates, and rule compliance (without writing story text). |
| **narrator.py** | The Storyteller. Takes the logical outcome from the Archivist and writes the prose/dialogue. |
| **cartographer.py** | Detects movement intent and renders the DOT graph for the map. |
| **scribe.py** | A background process that scans generated text for new NPCs or lore to add to the database. |
| **creator.py** | Used for "Genesis Mode" to generate the initial world and new entities on the fly. |

## Project Structure

![Agent Architecture Diagram](Untitled%20diagram-2025-12-01-202631.png)

## Quick Start

1.  **Clone the repository**.
2.  **Add your API Key**: Create a `.env` file in the root directory and add `GOOGLE_API_KEY=your_key_here`.
3.  **Run with Docker** (Recommended):
    ```bash
    docker build -t ai-dungeon .
    docker run -p 8080:8080 --env-file .env ai-dungeon
    ```
4.  **Play**: Open `http://localhost:8080` in your browser.

## Manual Installation (Local Python)

If you prefer not to use Docker, ensure you have Python 3.9+ and Graphviz installed on your system.

1.  **Install Graphviz**:
    * Windows: `winget install graphviz`
    * Mac: `brew install graphviz`
    * Linux: `sudo apt-get install graphviz`
2.  **Install Python Requirements**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the App**:
    ```bash
    streamlit run app.py
    ```

## Contributing

This is a hackathon/demo project. Feel free to fork it and add:

* **Image Generation**: Connect `illustrator.py` to an image API.
* **Database Support**: Replace the JSON file with SQLite or Firebase for better saves.
* **Combat System**: Expand `archivist.py` to handle dice rolls and complex stats.