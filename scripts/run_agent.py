from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent.config import AgentConfig
from agent.agent import run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Neo4j agent.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Show me all people",
        help="User question to send to the agent.",
    )
    args = parser.parse_args()

    cfg = AgentConfig.from_env()

    print(f"Sending: {args.prompt}\n")
    answer = run_agent(cfg, args.prompt)
    print(f"Response:\n{answer}")


if __name__ == "__main__":
    main()
