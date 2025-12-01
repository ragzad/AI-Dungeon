# Deployment Guide: AI Dungeon Master

This guide covers how to set up, configure, and deploy the AI Dungeon Master application. The app uses Python, Streamlit, and Google's Gemini API.

## Prerequisites

Before you begin, ensure you have the following:

1.  **Google Gemini API Key**: You need a valid API key from Google AI Studio.
    * Get one here: [Google AI Studio](https://aistudio.google.com/)
2.  **Python 3.9+** (for local execution).
3.  **Docker** (optional, for containerized deployment).
4.  **Graphviz**: (Optional but recommended) Required for the in-game map visualization.

---

## Configuration

The application relies on environment variables for authentication.

1.  Create a file named `.env` in the root directory.
2.  Add your Google API key to the file:

```ini
GOOGLE_API_KEY=your_actual_api_key_here