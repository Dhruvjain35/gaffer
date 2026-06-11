"""The Gaffer — coach agent wired to Arize Phoenix via the official MCP server.

Phoenix MCP gives the Gaffer its film room: traces, judge annotations, the
prompt registry, regression datasets and experiments. run_scrimmage is its
one custom tool — the promotion gate.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from agent.evals.scrimmage import run_scrimmage  # noqa: E402
from agent.gaffer.prompt import GAFFER_INSTRUCTION  # noqa: E402
from agent.instrumentation import setup_tracing  # noqa: E402

setup_tracing()

MODEL = os.environ.get("GAFFER_MODEL", os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"))

PHOENIX_TOOLS = [
    "list-projects",
    "list-traces",
    "get-trace",
    "get-spans",
    "get-span-annotations",
    "list-prompts",
    "get-latest-prompt",
    "get-prompt-version-by-tag",
    "list-prompt-versions",
    "upsert-prompt",
    "add-prompt-version-tag",
    "list-datasets",
    "get-dataset-examples",
    "add-dataset-examples",
    "list-experiments-for-dataset",
    "get-experiment-by-id",
]


def _phoenix_mcp() -> McpToolset:
    base_url = os.environ["PHOENIX_COLLECTOR_ENDPOINT"]
    api_key = os.environ["PHOENIX_API_KEY"]
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@arizeai/phoenix-mcp@latest", "--baseUrl", base_url, "--apiKey", api_key],
            ),
            timeout=60,
        ),
        tool_filter=PHOENIX_TOOLS,
    )


gaffer_agent = Agent(
    model=MODEL,
    name="the_gaffer",
    description="The coach: mines the Player's Phoenix traces, drills failures into a regression dataset, rewrites the playbook, and promotes it only after a winning scrimmage.",
    instruction=GAFFER_INSTRUCTION.format(
        project=os.environ.get("PHOENIX_PROJECT_NAME", "gaffer")
    ),
    tools=[_phoenix_mcp(), FunctionTool(func=run_scrimmage)],
)

root_agent = gaffer_agent
