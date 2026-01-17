from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import Agent, AgentConfig

from dotenv import load_dotenv
load_dotenv()

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Neo4j LangGraph agent against a prompt.")
    parser.add_argument(
        "prompt",
        help="User question to send to the agent (e.g. 'Виведи всі людей на їх прізвища').",
    )
    args = parser.parse_args()

    cfg = AgentConfig.from_env()
    agent = Agent(cfg)

    print(agent.graph.get_graph().draw_ascii())

    answer = agent.invoke(args.prompt)
    print(answer)


if __name__ == "__main__":
    main()
