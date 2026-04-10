# LLMThings v2 — Architecture

Refactored architecture of the LLMThings IoT deployment for the M2 CNS-SR
project. This version replaces the v1 push-based architecture (which was
rejected by the supervisor) with a pull-based, agent-driven design that
leaves real room for the future Energy & Transmission agent.

## What changed from v1

| Concern              | v1 (rejected)                          | v2 (this repo)                               |
|----------------------|----------------------------------------|----------------------------------------------|
| Default sensor state | All sensors active, push MQTT          | Fixed sensors in light_sleep, only badge pushes |
| Data flow            | ESP -> server (push)                   | Monitoring Agent -> ESP (pull, on demand)    |
| Network discovery    | Hard-coded registration                | Mesh / gossip discovery from a seed device   |
| Decision logic       | if/else in FastAPI routes              | Two LLMs (Monitoring + Orchestration)        |
| Inter-LLM dialogue   | None                                   | CrewAI, natural language, JSON answers       |
| Tool layer           | Hard-coded HTTP routes                 | MCP server with explicit tool sets per agent |

## Architecture overview

```
COUCHE 1 — Hardware
  Badge patient (toujours actif, MQTT push)
  ESP32 fixes (light_sleep par defaut, HTTP pull)
  Mosquitto broker

COUCHE 2 — MCP server (un seul, partage)
  Outils Monitoring  : discover_network, get_capabilities, get_health,
                       read_devices, write_device
  Outils Orchestration : read_devices, wake_up, put_to_sleep,
                         activate_service

COUCHE 3 — Agents CrewAI
  Monitoring Agent  : seul a pouvoir ecrire en BDD,
                      repond en JSON canonique
  Orchestration Agent : connait la carte, decide quoi reveiller,
                        delegue au Monitoring Agent en langage naturel

COUCHE 4 — Boucle externe (a venir)
  Listener MQTT du badge -> crew.kickoff() sur evenements
```

The two agents communicate **in natural language** via CrewAI's built-in
delegation mechanism (`allow_delegation=True` on the Orchestration Agent),
but the Monitoring Agent always answers with **structured JSON** matching
the canonical device shape.

## Folder layout

```
llmthings_v2/
├── docker-compose.yml          # mqtt + ollama + mcp_server + crew
├── mosquitto/                  # Mosquitto config
├── database/                   # SQLAlchemy models + CRUD layer
│   ├── schema.sql
│   ├── models.py               # Device, Service, Neighbor
│   └── device_registry.py      # CRUD + canonical JSON serialization
├── mcp_server/                 # MCP HTTP server (FastMCP, stateless)
│   ├── server.py
│   ├── esp32_client.py         # async HTTP client to talk to ESP32s
│   ├── Dockerfile
│   └── tools/
│       ├── monitoring_tools.py
│       └── orchestration_tools.py
├── crew/                       # CrewAI agents and crew
│   ├── agents.py               # Monitoring + Orchestration agents
│   ├── tasks.py
│   ├── crew.py                 # MCPServerAdapter wiring
│   ├── Dockerfile
│   └── requirements.txt
├── scripts/
│   ├── test_local.py             # smoke test of the database layer
│   ├── fake_esp32.py             # 4 fake ESP32s on ports 9001..4
│   ├── test_e2e_combined.py      # discovery + tools without CrewAI
│   ├── test_crew_connection.py   # CrewAI <-> MCP wiring (no LLM needed)
│   └── test_crew_e2e.py          # full end-to-end with Ollama
├── badge_firmware/
└── esp32_fixe_firmware/        # firmware for fixed sensors (next milestone)
    └── src/
        ├── main.ino
        ├── services/
        └── adapters/
```

## Test pyramid

The project has four layers of tests, going from "no dependencies" to
"full stack with the LLMs":

| Test                          | What it validates                          | Needs |
|-------------------------------|--------------------------------------------|-------|
| `test_local.py`               | Database CRUD and canonical JSON shape     | sqlalchemy |
| `test_e2e_combined.py`        | Discovery + tools against fake ESP32s      | + httpx, fastapi, uvicorn |
| `test_crew_connection.py`     | CrewAI <-> MCP wiring, tool discovery, tool invocation through CrewAI wrappers | + crewai, crewai-tools[mcp] |
| `test_crew_e2e.py`            | Full crew kickoff: 2 LLMs collaborating, delegation, real tool calls, real ESP32 responses | + Ollama with llama3.1 pulled |

Always go bottom-up: if `test_local` fails, no point running the higher
layers. If `test_crew_connection` passes but `test_crew_e2e` fails, the
problem is in the LLMs' reasoning or in Ollama, not in the wiring.

## Running

### Without Docker (recommended for development)

```bash
# Install everything once
pip install sqlalchemy httpx fastapi uvicorn
pip install -r mcp_server/requirements.txt
pip install -r crew/requirements.txt

# Run the lower-level tests
python -m scripts.test_local
python -m scripts.test_e2e_combined
python -m scripts.test_crew_connection

# For the full crew test you need Ollama running:
ollama serve &
ollama pull llama3.1
python -m scripts.test_crew_e2e
```

### With Docker (recommended for the demo)

```bash
docker compose up -d --build
docker compose logs -f mcp_server

# Run the crew end-to-end test inside the crew container
docker compose run --rm crew python -m scripts.test_crew_e2e
```

The first boot pulls llama3.1 (~5 GB) so it takes a while.

## Database write privileges

The database has **a single legitimate writer**: the Monitoring Agent,
through the `monitoring_*` tools. The `orchestration_*` tools expose
only `orchestration_read_devices` for queries; commands (`wake_up`,
`sleep`, `activate_service`) talk directly to the ESP32 over HTTP and
update the device's `status` field as a side effect, but never insert
new devices or rewrite their capabilities.

## How the two LLMs talk to each other

CrewAI handles this for us. When `allow_delegation=True` is set on an
agent, CrewAI silently injects a "delegate to coworker" tool into that
agent's toolbox. When the Orchestration Agent decides it needs
information from the Monitoring Agent, it calls that delegation tool
with a natural-language question, and CrewAI:

1. Forwards the question to the Monitoring Agent
2. Lets the Monitoring Agent reason and use its own MCP tools
3. Returns the Monitoring Agent's answer to the Orchestration Agent

The whole exchange is observable in the verbose logs, which is great
for the demo (you can literally show the two LLMs talking on screen).

## Next milestones

1. Fixed-sensor ESP32 firmware (`/capabilities`, `/health`, `/wake`,
   `/sleep`, `/activate_service`)
2. External MQTT listener triggering `crew.kickoff()` on badge events
3. Plan validation agent (energy/security)
4. Energy & transmission modelling agent
