from __future__ import annotations

import asyncio

from openai import AsyncOpenAI
from agents import Agent, Runner, set_default_openai_client, set_trace_processors
from langsmith.wrappers import OpenAIAgentsTracingProcessor

from agent.config import AgentConfig, configure_langsmith_env
from agent.prompts import SYSTEM_PROMPT_UK
from agent.tools import make_query_graph_db


def create_agent(cfg: AgentConfig, system_prompt: str | None = None) -> Agent:
    """
    Create an Agent using OpenAI Agents SDK with custom base_url.
    """
    configure_langsmith_env()

    # Set custom OpenAI client with base_url
    client = AsyncOpenAI(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
    )
    set_default_openai_client(client)

    # Create agent with tools
    agent = Agent(
        name="GraphAgent",
        instructions=system_prompt or SYSTEM_PROMPT_UK,
        model=cfg.model_name,
        tools=[make_query_graph_db(cfg)],
    )

    return agent


async def run_agent_async(cfg: AgentConfig, prompt: str, system_prompt: str | None = None) -> str:
    """
    Run the agent asynchronously and return the response.
    """
    agent = create_agent(cfg, system_prompt)
    result = await Runner.run(agent, prompt)
    return result.final_output


def run_agent(cfg: AgentConfig, prompt: str, system_prompt: str | None = None) -> str:
    """
    Run the agent synchronously and return the response.
    """
    set_trace_processors([OpenAIAgentsTracingProcessor()])
    return asyncio.run(run_agent_async(cfg, prompt, system_prompt))
