"""
tasks.py — CrewAI tasks.

For the v2 we expose ONE generic task: "satisfy a nurse's intent". The
intent itself is passed dynamically via the `inputs` of crew.kickoff().

Later milestones will introduce more specialised tasks (continuous
fall-detection loop, energy-aware re-planning, etc.).
"""

from crewai import Task, Agent


def build_orchestration_task(orchestration_agent: Agent) -> Task:
    return Task(
        description=(
            "A nurse just expressed the following intent in natural "
            "language:\n"
            "\n"
            '   "{intent}"\n'
            "\n"
            "Translate this intent into concrete actions on the IoT "
            "deployment. To do so:\n"
            "\n"
            "1. Identify which information you need about the deployment "
            "   to fulfill the intent (which devices? in which zones? "
            "   with which services?).\n"
            "2. Ask the Deployment Monitoring Agent for that information "
            "   in plain English. The Monitoring Agent will reply with "
            "   structured JSON describing the matching devices.\n"
            "3. Decide which devices must be woken up, in what order, "
            "   and which services must be activated on them.\n"
            "4. Use your tools to wake the devices and activate the "
            "   services. Do NOT wake devices you do not need.\n"
            "5. When the intent is satisfied, return a short report of "
            "   what you did and which devices are now active."
        ),
        expected_output=(
            "A short report (5–10 lines) listing:\n"
            "  - the devices you woke up\n"
            "  - the services you activated\n"
            "  - any device that failed to respond\n"
            "  - the final status of the deployment relevant to this intent"
        ),
        agent=orchestration_agent,
    )
