#!/usr/bin/env python3
"""Convert YAML plan output to human-readable text.

Usage:
    python format_plan.py plan.yaml
    python format_plan.py plan.yaml --plan 2     # show only plan 2
"""

import sys
import re
import argparse
import yaml


def slot_position(slot_name: str) -> str:
    """Extract position label from slot name (e.g. 'DM1' -> 'DM', 'GK' -> 'GK')."""
    return re.sub(r'\d+$', '', slot_name)


def slot_top_group(slot_name: str) -> str:
    """Guess top-level group from position label for display grouping.

    This is a simple heuristic — for proper grouping, the plan YAML
    would need to include the position tree. For now we read the group
    from the plan if available, or fall back to position label.
    """
    return slot_position(slot_name)


def format_lineup(xi: dict, group_order: list[str]) -> str:
    """Format a lineup dict (slot_name -> player_name) as grouped rows."""
    # Group slots by top-level position group
    groups: dict[str, list[tuple[str, str]]] = {}
    for slot_name, player_name in xi.items():
        pos = slot_position(slot_name)
        # Determine group: GK is its own group, otherwise use the first
        # character pattern. We'll group by the position label itself.
        groups.setdefault(pos, []).append((slot_name, player_name))

    lines = []
    # Order: try to follow the slot order from the xi dict
    seen = set()
    for slot_name in xi:
        pos = slot_position(slot_name)
        if pos in seen:
            continue
        seen.add(pos)
        entries = groups[pos]
        row = "  ".join(f"  {pos:3s}: {player}" for _, player in entries)
        lines.append(row)

    return "\n".join(lines)


def format_minutes(minutes: dict) -> str:
    """Format minutes dict as columnar display."""
    items = []
    for name in sorted(minutes):
        info = minutes[name]
        stints = info["stints"]
        total = info["total"]
        if not stints or total == 0:
            items.append(f"  {name}: 0")
        elif len(stints) == 1:
            items.append(f"  {name}: {stints[0]}")
        else:
            expr = " + ".join(str(x) for x in stints)
            items.append(f"  {name}: {expr} = {total}")

    col_width = max((len(i) for i in items), default=20) + 2
    lines = []
    for i in range(0, len(items), 3):
        lines.append("".join(item.ljust(col_width) for item in items[i:i + 3]))
    return "\n".join(lines)


def format_plan(plan: dict, plan_num: int, total: int) -> str:
    """Format a single plan dict as human-readable text."""
    out = []
    out.append(f"\n{'=' * 50}")
    out.append(f"=== PLAN {plan_num} of {total} ===")
    out.append(f"{'=' * 50}")

    xi = plan["starting_xi"]
    bench = plan.get("bench", [])
    subs = plan.get("substitutions", [])
    minutes = plan.get("minutes", {})

    # Build group order from starting XI slot order
    group_order = []
    for slot_name in xi:
        pos = slot_position(slot_name)
        if pos not in group_order:
            group_order.append(pos)

    out.append("\nStarting lineup:")
    out.append(format_lineup(xi, group_order))
    out.append(f"\n  Bench: {', '.join(bench) if bench else '(none)'}")

    if not subs:
        out.append("\n  No substitutions.")
    else:
        current_xi = dict(xi)
        current_bench = list(bench)
        for sub in subs:
            t = sub["time"]
            half_note = " (half time)" if t == 35 else ""
            out.append(f"\nSubstitution at {t} min{half_note}:")
            for swap in sub["swaps"]:
                on_p = swap["on"]
                off_p = swap["off"]
                slot = swap["slot"]
                pos = slot_position(slot)
                out.append(f"  {on_p} ON ({pos})  <->  {off_p} OFF")
                current_xi[slot] = on_p
                current_bench.remove(on_p)
                current_bench.append(off_p)
            out.append(format_lineup(current_xi, group_order))
            out.append(f"  Bench: {', '.join(current_bench)}")

    out.append("\nMinutes played:")
    out.append(format_minutes(minutes))

    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Format YAML plan as human-readable text.")
    parser.add_argument("plan_file", help="Path to plan YAML file")
    parser.add_argument("-o", "--output", default=None, help="Write output to this file")
    parser.add_argument("--plan", type=int, default=None, help="Show only this plan number")
    args = parser.parse_args()

    try:
        with open(args.plan_file) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: file '{args.plan_file}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error reading YAML: {e}")
        sys.exit(1)

    plans = data.get("plans", [])
    if not plans:
        print("No plans found in file.")
        sys.exit(1)

    duration = data.get("duration", "?")
    total = len(plans)

    lines = []
    if args.plan is not None:
        if args.plan < 1 or args.plan > total:
            print(f"Error: plan {args.plan} not found (file has {total} plans).")
            sys.exit(1)
        plan = plans[args.plan - 1]
        lines.append(f"Hockey Substitution Plan (from {data.get('game_file', '?')}, {duration} min)")
        lines.append(format_plan(plan, args.plan, total))
    else:
        lines.append(f"Hockey Substitution Plans (from {data.get('game_file', '?')}, {duration} min)")
        for plan in plans:
            lines.append(format_plan(plan, plan["plan_number"], total))
        lines.append(f"\n{'=' * 50}")
        lines.append(f"Showing {total} plan(s).")

    text = "\n".join(lines)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text + "\n")
        print(f"Written to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
