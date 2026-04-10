"""
agents.py — CrewAI agent definitions for the LLMThings deployment.

Two agents collaborate:

  - monitoring_agent     : the eyes of the system. Knows the deployment
                           state via the `monitoring_*` tools. ONLY agent
                           allowed to write to the database. Answers
                           Orchestration questions in JSON.

  - orchestration_agent  : the brain. Knows the map and the user intents.
                           Decides which devices to wake, when, and in
                           what order. Asks the Monitoring Agent for
                           availability info, then issues commands via
                           the `orchestration_*` tools.

Both agents share the SAME local Ollama LLM by default but each can be
swapped to a different model via env vars without touching this file.
"""

import os
from crewai import Agent, LLM


# ─────────────────────────────────────────────────────────────────
# LLM configuration
# ─────────────────────────────────────────────────────────────────
# CrewAI 1.x has multiple routing paths for LLMs. The cleanest one for
# Ollama is the OpenAI-compatible provider, which reads its base URL
# from the OLLAMA_HOST environment variable. We set BOTH:
#   - OLLAMA_HOST   (used by CrewAI's OpenAICompatibleCompletion)
#   - OPENAI_API_KEY  (placeholder, otherwise the OpenAI client may
#                      try to reach api.openai.com if anything goes
#                      wrong upstream)
#
# Set OLLAMA_BASE_URL in your environment (default: http://localhost:11434).
# Both `http://host:port` and `http://host:port/v1` are accepted —
# CrewAI normalizes the URL to add /v1 if missing.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Make sure CrewAI's OpenAI-compatible Ollama provider sees our URL.
# `OLLAMA_HOST` is the canonical env var that the provider checks.
os.environ.setdefault("OLLAMA_HOST", OLLAMA_BASE_URL)

# Avoid any accidental fallback to the real OpenAI API.
# Ollama doesn't need a real key, but the OpenAI SDK refuses to
# instantiate a client without one.
os.environ.setdefault("OPENAI_API_KEY", "ollama-no-key-needed")

MONITORING_MODEL    = os.getenv("MONITORING_MODEL",    "ollama/llama3.1")
ORCHESTRATION_MODEL = os.getenv("ORCHESTRATION_MODEL", "ollama/llama3.1")


def make_llm(model: str) -> LLM:
    """Build a CrewAI LLM bound to the local Ollama server.

    We pass `base_url` explicitly so the OpenAI-compatible client
    inside CrewAI knows where to send requests, regardless of the
    OLLAMA_HOST env var. We also set a low temperature for more
    deterministic tool calling.
    """
    return LLM(
        model=model,
        base_url=OLLAMA_BASE_URL,
        api_key="ollama-no-key-needed",
        temperature=0.1,
    )


# ─────────────────────────────────────────────────────────────────
# Agent factories
# ─────────────────────────────────────────────────────────────────
# We expose factories instead of module-level instances because the
# tools list is only known once the MCP server adapter has connected.
# The crew bootstrap (see crew.py) creates the adapter, filters the
# tools per agent, then calls these factories.

def build_monitoring_agent(monitoring_tools: list) -> Agent:
    return Agent(
        role="Deployment Monitoring Agent",
        goal=(
            "Maintain an accurate, real-time view of the LLMThings IoT "
            "deployment in a nursing home. Answer the Orchestration "
            "Agent's questions about device availability, location, "
            "status and capabilities by returning a structured JSON "
            "object — never plain prose."
        ),
        backstory=(
            "You are the eyes of the LLMThings system. You know how to "
            "discover devices via mesh starting from a seed ESP32, you "
            "can probe their /capabilities and /health endpoints on "
            "demand, and you maintain the ground-truth deployment "
            "database. You are the ONLY component allowed to write to "
            "the database — other agents must ask you for information.\n"
            "\n"
            "=== IMPORTANT: service vocabulary ===\n"
            "In this deployment, services have SHORT canonical names. "
            "You MUST use exactly these names when filtering by service:\n"
            "  - 'camera'  : any video streaming or image capture service\n"
            "  - 'pir'     : passive infrared presence detector\n"
            "  - 'imu'     : inertial measurement unit (accelerometer,\n"
            "                used for fall detection on the patient badge)\n"
            "  - 'sound'   : microphone / sound-level sensor\n"
            "\n"
            "If a user or another agent asks about 'video streaming', "
            "'video stream', 'cameras', 'footage', etc., you MUST translate "
            "that to service='camera' when calling monitoring_read_devices. "
            "Never pass 'video_stream' or 'video_streaming' — the database "
            "will return zero results.\n"
            "\n"
            "=== IMPORTANT: zone vocabulary ===\n"
            "Zones are: corridor, activity_node, kitchen, living, bedroom, "
            "garden, outside.\n"
            "\n"
            "=== Output format ===\n"
            "When you answer a question, you ALWAYS return a JSON object "
            "with the canonical device shape, never natural-language "
            "prose:\n"
            "{\n"
            '  "device_id" : "esp32-001",\n'
            '  "ip"        : "192.168.1.42",\n'
            '  "status"    : "light_sleep",\n'
            '  "location"  : { "zone": "corridor", "x": 3.5, "y": 1.2, "z": 0.0 },\n'
            '  "services"  : [ ... ],\n'
            '  "neighbors" : ["esp32-002", "esp32-003"]\n'
            "}\n"
            "\n"
            "If the question matches several devices, return a JSON "
            "array. If it matches none, return an empty array []. "
            "Do NOT invent devices that are not in the database."
        ),
        tools=monitoring_tools,
        llm=make_llm(MONITORING_MODEL),
        allow_delegation=False,
        verbose=True,
        max_iter=8,
    )


def build_orchestration_agent(orchestration_tools: list) -> Agent:
    return Agent(
        role="Orchestration Agent",
        goal=(
            "Translate natural-language intents from nurses into a "
            "progressive activation plan of IoT devices. Wake the "
            "minimum number of sensors necessary to satisfy the intent, "
            "and put devices back to sleep as soon as they are no longer "
            "needed."
        ),
        backstory=(
            "You receive natural-language intents from nurses in a "
            "nursing home. You know the map of the building and the "
            "paths a patient might take, but you do NOT know the live "
            "state of the IoT devices.\n"
            "\n"
            "=== IMPORTANT: service vocabulary ===\n"
            "Services in the deployment have SHORT canonical names:\n"
            "  - 'camera'  : video streaming / image capture\n"
            "  - 'pir'     : presence detector\n"
            "  - 'imu'     : accelerometer, used for fall detection\n"
            "  - 'sound'   : microphone\n"
            "When a nurse talks about 'video', 'streaming', 'footage', etc., "
            "that always maps to the service named 'camera'. When they talk "
            "about 'presence' or 'motion', that's 'pir'. When they talk "
            "about 'falls' or 'movement', that's 'imu'.\n"
            "\n"
            "=== How to fulfill an intent ===\n"
            "1. Ask the Deployment Monitoring Agent which devices are "
            "   available in the relevant zone, with the relevant service. "
            "   Phrase the question clearly in plain English and let the "
            "   Monitoring Agent translate it to the canonical service "
            "   names.\n"
            "2. The Monitoring Agent will reply with a JSON array of "
            "   devices. NEVER invent device IDs. Use ONLY the device_id "
            "   values returned by the Monitoring Agent.\n"
            "3. For each device you need: call orchestration_wake_up_device "
            "   with its device_id, then call orchestration_activate_service "
            "   with its device_id and the canonical service name.\n"
            "4. Respect least energy: do not wake devices you do not need.\n"
            "5. When done, write a short report listing exactly what you "
            "   did and what is now active."
        ),
        tools=orchestration_tools,
        llm=make_llm(ORCHESTRATION_MODEL),
        allow_delegation=True,
        verbose=True,
        max_iter=10,
    )
