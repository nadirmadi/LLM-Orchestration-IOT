"""
crew.py — Bootstraps the LLMThings crew.

Responsibilities:
  1. Connect to the MCP server over streamable HTTP via MCPServerAdapter
  2. Split the discovered tools into the Monitoring set and the
     Orchestration set, based on their name prefix
  3. Build the two agents with their respective tools
  4. Build a hierarchical Crew where the Orchestration Agent is the
     manager that can delegate to the Monitoring Agent

Usage (see also scripts/test_crew.py):

    from crew.crew import build_crew_from_mcp

    with build_crew_from_mcp() as crew:
        result = crew.kickoff(inputs={
            "intent": "Which devices are available in the corridor "
                      "and can stream video?"
        })
        print(result)
"""

import os
from contextlib import contextmanager
from typing import Iterator

from crewai import Crew, Process
from crewai_tools import MCPServerAdapter

from .agents import build_monitoring_agent, build_orchestration_agent
from .tasks  import build_orchestration_task


MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8765/mcp/")


def split_tools_by_prefix(all_tools: list) -> tuple[list, list]:
    """Partition the MCP tools into the Monitoring set (`monitoring_*`)
    and the Orchestration set (`orchestration_*`)."""
    monitoring    = [t for t in all_tools if t.name.startswith("monitoring_")]
    orchestration = [t for t in all_tools if t.name.startswith("orchestration_")]
    return monitoring, orchestration


@contextmanager
def build_crew_from_mcp(mcp_url: str = MCP_SERVER_URL) -> Iterator[Crew]:
    """Context manager that opens the MCP connection, builds the crew,
    yields it for the caller to kickoff, and cleans up the connection
    on exit. Use it with a `with` statement."""
    server_params = {
        "url":       mcp_url,
        "transport": "streamable-http",
    }

    with MCPServerAdapter(server_params) as all_tools:
        print(f"[crew] Connected to MCP. Tools: {[t.name for t in all_tools]}")

        monitoring_tools, orchestration_tools = split_tools_by_prefix(all_tools)

        # Sanity check
        if not monitoring_tools:
            raise RuntimeError("No monitoring_* tools found on the MCP server")
        if not orchestration_tools:
            raise RuntimeError("No orchestration_* tools found on the MCP server")

        monitoring_agent    = build_monitoring_agent(monitoring_tools)
        orchestration_agent = build_orchestration_agent(orchestration_tools)

        task = build_orchestration_task(orchestration_agent)

        crew = Crew(
            agents=[monitoring_agent, orchestration_agent],
            tasks=[task],
            # Hierarchical: a manager (the Orchestration Agent, set as
            # the task owner) decides when to delegate to the Monitoring
            # Agent. CrewAI handles the natural-language hand-off.
            process=Process.sequential,
            verbose=True,
        )

        yield crew
