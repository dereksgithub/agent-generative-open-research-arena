#!/usr/bin/env python3
"""Analyze an AGORA simulation run output directory.

Usage:
    python scripts/analyze_run.py <run-output-dir>

Example:
    agora run scenarios/examples/morning_commute.yaml --seed 42 --no-llm
    python scripts/analyze_run.py runs/morning_commute/20260402_182302/

This script reads the structured outputs and prints a summary report.
It demonstrates how researchers can build downstream analysis from AGORA outputs.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    run_dir = Path(sys.argv[1])
    if not run_dir.is_dir():
        print(f"Error: {run_dir} is not a directory", file=sys.stderr)
        return 1

    print(f"{'=' * 60}")
    print(f"AGORA Run Analysis: {run_dir}")
    print(f"{'=' * 60}\n")

    # -- Metadata --
    meta_path = run_dir / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        print("Run Metadata")
        print(f"  Run ID:        {meta.get('run_id', 'N/A')}")
        print(f"  Scenario:      {meta.get('scenario_name', 'N/A')} ({meta.get('scenario_id', '')})")
        print(f"  Domain:        {meta.get('domain', 'N/A')}")
        print(f"  Decision Mode: {meta.get('decision_mode', 'N/A')}")
        print(f"  Seed:          {meta.get('seed', 'N/A')}")
        print(f"  Ticks:         {meta.get('total_ticks', 'N/A')}")
        print(f"  Agents:        {meta.get('total_agents', 'N/A')}")
        print(f"  Decisions:     {meta.get('total_decisions', 'N/A')}")
        print()

    # -- Agent Summary --
    summary_path = run_dir / "agent_summary.csv"
    if summary_path.exists():
        print("Agent Summary")
        print(f"  {'Agent':<12} {'Role':<12} {'Trips':<8} {'Stays':<8} {'Modes':<8}")
        print(f"  {'-' * 48}")
        with summary_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                print(
                    f"  {row['agent_name']:<12} {row['role']:<12} "
                    f"{row['total_trips']:<8} {row['total_stays']:<8} "
                    f"{row['unique_modes_used']:<8}"
                )
        print()

    # -- Aggregate Travel Patterns --
    agg_path = run_dir / "aggregate.csv"
    if agg_path.exists():
        print("Travel Patterns by Tick")
        travel_ticks = []
        with agg_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                tc = int(row["travel_count"])
                if tc > 0:
                    travel_ticks.append((int(row["tick"]), tc, int(row["stay_count"])))

        if travel_ticks:
            print(f"  {'Tick':<8} {'Travel':<10} {'Stay':<10}")
            print(f"  {'-' * 28}")
            for tick, travel, stay in travel_ticks:
                bar = "#" * travel
                print(f"  {tick:<8} {travel:<10} {stay:<10} {bar}")
        else:
            print("  No travel occurred during this run.")
        print()

    # -- Decision Mode Breakdown --
    decisions_path = run_dir / "decisions.jsonl"
    if decisions_path.exists():
        mode_counter: Counter[str] = Counter()
        action_counter: Counter[str] = Counter()
        with decisions_path.open() as f:
            for line in f:
                d = json.loads(line)
                action_counter[d["action"]] += 1
                mode = d.get("metadata", {}).get("mode", "")
                if mode:
                    mode_counter[mode] += 1

        print("Decision Breakdown")
        print(f"  Actions: {dict(action_counter)}")
        if mode_counter:
            total_modal = sum(mode_counter.values())
            print(f"  Mode split:")
            for mode, count in mode_counter.most_common():
                pct = count / total_modal * 100
                print(f"    {mode:<12} {count:>4} ({pct:.1f}%)")
        print()

    # -- KPIs --
    kpi_path = run_dir / "kpis.json"
    if kpi_path.exists():
        kpi_data = json.loads(kpi_path.read_text())
        kpis = kpi_data.get("kpis", {})
        if kpis:
            print("KPI Results")
            for kpi_id, kpi in kpis.items():
                name = kpi.get("name", kpi_id)
                overall = kpi.get("overall", "N/A")
                unit = kpi.get("unit", "")
                if unit == "%" and isinstance(overall, (int, float)):
                    overall = f"{overall * 100:.1f}"
                print(f"  {name}: {overall} {unit}")
            print()

    # -- Narrative Samples --
    narr_path = run_dir / "narratives.jsonl"
    if narr_path.exists():
        narratives = []
        with narr_path.open() as f:
            for line in f:
                d = json.loads(line)
                if d.get("action") == "travel":
                    narratives.append(d)

        if narratives:
            print("Sample Decision Narratives (first 5 travel decisions)")
            for n in narratives[:5]:
                print(f"  Tick {n['tick']} | {n['agent_id']}: {n['reasoning']}")
            print()

    print(f"{'=' * 60}")
    print("Analysis complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
