"""
diagnose_ollama.py — Step-by-step diagnostic for the CrewAI <-> Ollama
connection. Run this INSIDE the crew container if test_crew_e2e fails:

    docker compose run --rm crew python -m scripts.diagnose_ollama

It will tell you exactly which step is broken:
    1. Are the env vars set correctly?
    2. Can the container reach Ollama at all (HTTP)?
    3. Is the requested model pulled in Ollama?
    4. Does CrewAI build the LLM with the right base URL?
    5. Can CrewAI actually call the LLM and get a response?
"""

import os
import sys
import json
import urllib.request
import urllib.error


def section(title: str):
    print()
    print("─" * 70)
    print(title)
    print("─" * 70)


# ─────────────────────────────────────────────────────────────────
# 1. Environment variables
# ─────────────────────────────────────────────────────────────────
section("1. Environment variables")

vars_to_check = [
    "OLLAMA_BASE_URL",
    "OLLAMA_HOST",
    "OPENAI_API_KEY",
    "MONITORING_MODEL",
    "ORCHESTRATION_MODEL",
    "MCP_SERVER_URL",
]
for v in vars_to_check:
    val = os.getenv(v, "<not set>")
    # Truncate long values
    if len(val) > 60:
        val = val[:57] + "..."
    print(f"  {v:25} = {val}")

ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
print(f"\n  Will use Ollama at: {ollama_base}")


# ─────────────────────────────────────────────────────────────────
# 2. Reach Ollama HTTP
# ─────────────────────────────────────────────────────────────────
section("2. Can we reach Ollama over HTTP?")

try:
    url = f"{ollama_base.rstrip('/')}/api/tags"
    with urllib.request.urlopen(url, timeout=5) as r:
        data = json.loads(r.read().decode())
        models = [m["name"] for m in data.get("models", [])]
        print(f"  OK — Ollama answered. {len(models)} models pulled:")
        for m in models:
            print(f"    - {m}")
except urllib.error.URLError as e:
    print(f"  FAILED to reach {url}")
    print(f"  Error: {e}")
    print()
    print("  This usually means:")
    print("    - Ollama container is not running, or")
    print("    - The OLLAMA_BASE_URL points to the wrong host")
    print("    - Inside Docker, use http://ollama:11434, not localhost")
    sys.exit(1)
except Exception as e:
    print(f"  Unexpected error: {type(e).__name__}: {e}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────
# 3. Is the requested model available?
# ─────────────────────────────────────────────────────────────────
section("3. Is the requested model pulled?")

requested = os.getenv("MONITORING_MODEL", "ollama/llama3.1")
# Strip the "ollama/" prefix if present
requested_short = requested.split("/", 1)[-1]
# llama3.1 might appear as "llama3.1:latest" in ollama list
matching = [m for m in models if m.split(":")[0] == requested_short.split(":")[0]]
if matching:
    print(f"  OK — model '{requested_short}' is available as: {matching}")
else:
    print(f"  FAILED — model '{requested_short}' is not pulled.")
    print(f"  Run inside the ollama container:")
    print(f"      docker compose exec ollama ollama pull {requested_short}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────
# 4. Build the LLM via crew.agents.make_llm
# ─────────────────────────────────────────────────────────────────
section("4. Build the LLM via crew.agents.make_llm")

try:
    from crew.agents import make_llm, MONITORING_MODEL
    llm = make_llm(MONITORING_MODEL)
    print(f"  LLM type    : {type(llm).__name__}")
    print(f"  LLM module  : {type(llm).__module__}")
    print(f"  LLM model   : {getattr(llm, 'model', '?')}")
    print(f"  LLM base_url: {getattr(llm, 'base_url', '?')}")
    api_key = str(getattr(llm, 'api_key', '?'))
    print(f"  LLM api_key : {api_key[:30]}{'...' if len(api_key) > 30 else ''}")

    expected_provider = "OpenAICompatibleCompletion"
    if type(llm).__name__ != expected_provider:
        print()
        print(f"  WARNING — expected provider {expected_provider!r}, "
              f"got {type(llm).__name__!r}")
        print("  CrewAI may have routed your model to the wrong provider.")
except Exception as e:
    print(f"  FAILED — {type(e).__name__}: {e}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────
# 5. Real LLM call
# ─────────────────────────────────────────────────────────────────
section("5. Real LLM call (this hits Ollama)")

try:
    answer = llm.call([
        {"role": "user", "content": "Reply with the single word: pong"}
    ])
    print(f"  Ollama replied: {answer!r}")
    if "pong" in str(answer).lower():
        print("  OK — round-trip works!")
    else:
        print("  WARNING — got an answer but it does not contain 'pong'.")
        print("  The model may be too small or the prompt format is wrong.")
except Exception as e:
    print(f"  FAILED — {type(e).__name__}: {e}")
    print()
    print("  Common causes:")
    print("    - Ollama container is not yet ready (check `docker compose logs ollama`)")
    print("    - The model is too large to load on your machine")
    print("    - CrewAI is sending requests to the wrong URL")
    sys.exit(1)


print()
print("═" * 70)
print("  ALL DIAGNOSTIC STEPS PASSED — you can run test_crew_e2e.py now")
print("═" * 70)
