from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from agent.config import AgentConfig
from agent.corruption_agent import CorruptionDetectionAgent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the family relationship agent for a target person."
    )
    parser.add_argument(
        "target",
        help=(
            "Target person to investigate (name, RNOKPP, or other identifier). "
            "Example: 'Іванов Іван Іванович' or '1234567890'"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path for JSON results (optional). If not specified, prints to stdout.",
        default=None,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show full output including internal messages.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("FAMILY RELATIONSHIP AGENT")
    print("=" * 60)
    print(f"Target: {args.target}")
    print("=" * 60)
    print()

    cfg = AgentConfig.from_env()
    agent = CorruptionDetectionAgent(cfg)

    print("Agent Graph Structure:")
    print(agent.get_graph_visualization())
    print()

    print("Starting family relationship discovery...")
    print("-" * 40)

    if args.verbose:
        result = agent.invoke(args.target)
        output = {
            "target_person_query": result.get("target_person_query"),
            "family_relationships": result.get("family_relationships"),
            "person_ids": result.get("person_ids"),
            # Serialize messages to plain text to keep JSON output safe
            "messages": [
                getattr(m, "content", str(m)) if m is not None else None
                for m in result.get("messages", [])
            ],
        }
    else:
        output = agent.get_family_data(args.target)

    output_json = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"\nResults saved to: {args.output}")
    else:
        print("\nResults:")
        print("-" * 40)
        print(output_json)

    if isinstance(output, dict):
        family = output.get("family_relationships", {})
        persons = output.get("person_ids", [])
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Family members found: {len(persons)}")
        if isinstance(family, dict) and family.get("target_person"):
            print(f"Target person ID: {family.get('target_person', {}).get('person_id', 'N/A')}")
            print(f"Target name: {family.get('target_person', {}).get('full_name', 'N/A')}")


if __name__ == "__main__":
    main()
