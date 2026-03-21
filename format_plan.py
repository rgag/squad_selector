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


def format_timeline_segment(seg: dict) -> str:
    """Format a single timeline segment."""
    if seg["type"] == "bench":
        return f"bench({seg['minutes']})"
    else:
        return f"{seg['position']}({seg['minutes']})"


def format_minutes(minutes: dict) -> str:
    """Format minutes dict showing each player's timeline and total."""
    lines = []
    name_width = max((len(name) for name in minutes), default=5) + 2
    for name in sorted(minutes):
        info = minutes[name]
        total = info["total"]
        timeline = info.get("timeline", [])
        if timeline:
            segments = " -> ".join(format_timeline_segment(seg) for seg in timeline)
            lines.append(f"  {name:<{name_width}} {segments}  = {total} min")
        elif total == 0:
            lines.append(f"  {name:<{name_width}} 0 min")
        else:
            lines.append(f"  {name:<{name_width}} {total} min")
    return "\n".join(lines)


def format_summary_grid(plan: dict, duration: int) -> str:
    """Build a grid showing each player's position in each period."""
    xi = plan["starting_xi"]
    bench = plan.get("bench", [])
    subs = plan.get("substitutions", [])

    # Determine period boundaries
    sub_times = [s["time"] for s in subs]
    boundaries = [0] + sub_times + [duration]
    periods = [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]

    # Track slot->player at each period
    slot_to_player = dict(xi)
    all_players = list(xi.values()) + list(bench)

    # Build: for each period, which position is each player in?
    grid: dict[str, list[str]] = {p: [] for p in all_players}

    # Period 0: starting state
    on_pitch = dict(xi)  # slot -> player
    player_to_slot = {v: k for k, v in xi.items()}
    for p in bench:
        player_to_slot[p] = None

    for period_idx, (start, end) in enumerate(periods):
        # Apply subs that happen at the start of this period (except period 0)
        if period_idx > 0:
            sub = subs[period_idx - 1]
            for swap in sub["swaps"]:
                on_p = swap["on"]
                off_p = swap["off"]
                slot = swap["slot"]
                on_pitch[slot] = on_p
                player_to_slot[on_p] = slot
                player_to_slot[off_p] = None

        for p in all_players:
            slot = player_to_slot.get(p)
            if slot is not None:
                grid[p].append(slot_position(slot))
            else:
                grid[p].append("bench")

    # Format as table
    period_headers = [f"{s}-{e}" for s, e in periods]
    name_width = max(len(p) for p in all_players) + 2
    col_width = max(max(len(h) for h in period_headers), 5) + 2

    lines = []
    header = " " * name_width + "".join(h.ljust(col_width) for h in period_headers)
    lines.append(header)
    for p in all_players:
        row = f"{p:<{name_width}}" + "".join(cell.ljust(col_width) for cell in grid[p])
        lines.append(row)

    return "\n".join(lines)


def format_plan(plan: dict, plan_num: int, total: int, duration: int = 0, equal_periods: bool = False) -> str:
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

    if equal_periods and subs and duration > 0:
        out.append("\nSummary:")
        out.append(format_summary_grid(plan, duration))

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

    duration = data.get("duration", 0)
    equal_periods = data.get("equal_periods", False)
    total = len(plans)

    lines = []
    if args.plan is not None:
        if args.plan < 1 or args.plan > total:
            print(f"Error: plan {args.plan} not found (file has {total} plans).")
            sys.exit(1)
        plan = plans[args.plan - 1]
        lines.append(f"Hockey Substitution Plan (from {data.get('game_file', '?')}, {duration} min)")
        lines.append(format_plan(plan, args.plan, total, duration, equal_periods))
    else:
        lines.append(f"Hockey Substitution Plans (from {data.get('game_file', '?')}, {duration} min)")
        for plan in plans:
            lines.append(format_plan(plan, plan["plan_number"], total, duration, equal_periods))
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
