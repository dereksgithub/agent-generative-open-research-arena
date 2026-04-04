#!/usr/bin/env python3
"""assemble_personas.py — Read agent persona .md files and emit a complete scenario YAML.

Usage:
    python scripts/assemble_personas.py personas/demo/ \
        --template scenarios/templates/commute_base.yaml \
        --output scenarios/generated/demo_commute.yaml
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


def parse_persona_md(path: Path) -> dict:
    """Parse a persona .md file into a dict compatible with AGORA's PersonaDefinition."""
    text = path.read_text(encoding="utf-8")
    persona: dict = {}

    # Extract the agent name from the first heading
    name_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if name_match:
        full_name = name_match.group(1).strip()
        persona["name"] = full_name
        # Derive id from first name, lowercased
        persona["id"] = full_name.split()[0].lower()

    # Parse key-value pairs from **Key:** value lines
    # Handles both **Key:** value (colon inside bold) and **Key**: value (colon outside)
    kv_pattern = re.compile(r"\*\*(.+?):\*\*\s*(.+)")
    kv_pattern_alt = re.compile(r"\*\*(.+?)\*\*:\s*(.+)")
    kv_map: dict[str, str] = {}
    for m in kv_pattern.finditer(text):
        key = m.group(1).strip().lower().replace(" ", "_")
        val = m.group(2).strip()
        kv_map[key] = val
    for m in kv_pattern_alt.finditer(text):
        key = m.group(1).strip().lower().replace(" ", "_")
        val = m.group(2).strip()
        if key not in kv_map:
            kv_map[key] = val

    persona["role"] = kv_map.get("role", "")
    persona["home_location"] = kv_map.get("home_location", "")
    persona["work_location"] = kv_map.get("work_location", "")
    persona["preferred_mode"] = kv_map.get("preferred_mode", "walk")

    age = kv_map.get("age")
    if age and age.isdigit():
        persona["age"] = int(age)

    persona["income_bracket"] = kv_map.get("income", "")
    hs = kv_map.get("household_size")
    if hs and hs.isdigit():
        persona["household_size"] = int(hs)

    # Parse bulleted lists under known sections
    sections = _extract_sections(text)

    persona["traits"] = _parse_bullet_list(sections.get("traits", ""))
    persona["values"] = _parse_bullet_list(sections.get("values", ""))

    # Build rich backstory from multiple sections
    backstory_parts: list[str] = []

    bs = sections.get("backstory", "").strip()
    if bs:
        backstory_parts.append(bs)

    principles = sections.get("behaviour_principles", "") or sections.get("behavior_principles", "")
    if principles.strip():
        backstory_parts.append("\n\nBehaviour principles:\n" + principles.strip())

    memory = sections.get("memory_seeds", "")
    if memory.strip():
        backstory_parts.append("\n\nPast experiences:\n" + memory.strip())

    persona["backstory"] = "\n".join(backstory_parts).strip()

    return persona


def _extract_sections(text: str) -> dict[str, str]:
    """Split markdown into sections by ## headings."""
    sections: dict[str, str] = {}
    current_key = ""
    current_lines: list[str] = []

    for line in text.split("\n"):
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            if current_key:
                sections[current_key] = "\n".join(current_lines)
            current_key = heading_match.group(1).strip().lower().replace(" ", "_").replace("&", "and")
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines)

    return sections


def _parse_bullet_list(text: str) -> list[str]:
    """Extract items from a markdown bullet list."""
    items: list[str] = []
    for line in text.split("\n"):
        m = re.match(r"^\s*[-*]\s+(.+)", line)
        if m:
            items.append(m.group(1).strip())
    return items


def assemble_scenario(
    persona_dir: Path,
    template_path: Path,
    output_path: Path,
) -> None:
    """Read persona .md files and merge them into a scenario template."""
    # Load the base scenario template (has locations, routes, interventions, kpis)
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))

    # Parse all persona files
    md_files = sorted(persona_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md persona files found in {persona_dir}")

    agents = []
    for md_path in md_files:
        persona = parse_persona_md(md_path)
        agents.append(persona)
        print(f"  Loaded persona: {persona.get('name', '?')} ({md_path.name})")

    template["agents"] = agents

    # Update agent count info in description if present
    if "description" in template:
        template["description"] = re.sub(
            r"\d+ (residents|agents|people)",
            f"{len(agents)} agents",
            template.get("description", ""),
        )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"# Auto-generated from {persona_dir.name}/ personas + {template_path.name}\n")
        f.write(f"# {len(agents)} agents assembled\n\n")
        yaml.dump(template, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nScenario written: {output_path} ({len(agents)} agents)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble persona .md files into an AGORA scenario")
    parser.add_argument("persona_dir", type=Path, help="Directory containing agent .md files")
    parser.add_argument("--template", type=Path, required=True, help="Base scenario YAML template")
    parser.add_argument("--output", type=Path, required=True, help="Output scenario YAML path")
    args = parser.parse_args()

    assemble_scenario(args.persona_dir, args.template, args.output)


if __name__ == "__main__":
    main()
