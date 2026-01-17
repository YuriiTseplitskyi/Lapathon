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
    print("CORRUPTION DETECTION AGENT")
    print("=" * 60)
    print(f"Target: {args.target}")
    print("=" * 60)
    print()

    cfg = AgentConfig.from_env()
    agent = CorruptionDetectionAgent(cfg)

    print("Agent Graph Structure:")
    print(agent.get_graph_visualization())
    print()

    print("Starting corruption detection analysis...")
    print("-" * 40)

    result = agent.invoke(args.target)

    if args.verbose:
        output = {
            "target_person_query": result.get("target_person_query"),
            "family_relationships": result.get("family_relationships"),
            "person_ids": result.get("person_ids"),
            "income_assets_analysis": result.get("income_assets_analysis"),
            "proxy_ownership_analysis": result.get("proxy_ownership_analysis"),
            # Serialize messages to plain text to keep JSON output safe
            "messages": [
                getattr(m, "content", str(m)) if m is not None else None
                for m in result.get("messages", [])
            ],
        }
    else:
        output = {
            "target_person_query": result.get("target_person_query"),
            "family_relationships": result.get("family_relationships"),
            "person_ids": result.get("person_ids"),
            "income_assets_analysis": result.get("income_assets_analysis"),
            "proxy_ownership_analysis": result.get("proxy_ownership_analysis"),
        }

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
        income_assets = output.get("income_assets_analysis", {})
        proxy_ownership = output.get("proxy_ownership_analysis", {})

        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Family members found: {len(persons)}")
        if isinstance(family, dict) and family.get("target_person"):
            print(f"Target person ID: {family.get('target_person', {}).get('person_id', 'N/A')}")
            print(f"Target name: {family.get('target_person', {}).get('full_name', 'N/A')}")

        # Show income/assets summary
        if isinstance(income_assets, dict) and income_assets.get("risk_level"):
            print()
            print("INCOME VS ASSETS ANALYSIS:")
            print(f"  Risk Level: {income_assets.get('risk_level', 'N/A')}")
            if income_assets.get("summary"):
                print(f"  Summary: {income_assets.get('summary')}")
            if income_assets.get("income_assets_ratio"):
                print(f"  Assets/Income Ratio: {income_assets.get('income_assets_ratio')}x")

        # Show proxy ownership summary
        if isinstance(proxy_ownership, dict) and proxy_ownership.get("proxy_ownership_detected"):
            print()
            print("PROXY OWNERSHIP ANALYSIS:")
            print(f"  Detected: {proxy_ownership.get('proxy_ownership_detected', False)}")
            print(f"  Confidence: {proxy_ownership.get('confidence_level', 'N/A')}")
            if proxy_ownership.get("summary"):
                print(f"  Summary: {proxy_ownership.get('summary')}")
            if proxy_ownership.get("proxy_owners"):
                print(f"  Proxy Owners Found: {len(proxy_ownership.get('proxy_owners', []))}")
            if proxy_ownership.get("suspected_beneficiaries"):
                print(f"  Suspected Beneficiaries: {len(proxy_ownership.get('suspected_beneficiaries', []))}")


if __name__ == "__main__":
    main()
