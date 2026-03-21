#!/usr/bin/env python3
"""Validate a plan YAML against the game YAML constraints.

Usage:
    python validate_plan.py game.yaml plan.yaml
    python validate_plan.py game.yaml plan.yaml --plan 2   # validate only plan 2
"""

import sys
import argparse
import yaml
from hockey_planner import load_config


def validate_plan(plan: dict, game: dict, players: list, tree, slots: list[dict]) -> list[str]:
    """Validate a single plan. Returns a list of error strings (empty = pass)."""
    errors = []
    players_by_name = {p.name: p for p in players}
    duration = game["duration"]
    never_bench_together = game.get("never_bench_together", [])
    slot_type_map = {s["name"]: s["type"] for s in slots}
    all_slot_names = set(s["name"] for s in slots)

    xi = plan.get("starting_xi", {})
    bench = plan.get("bench", [])
    subs = plan.get("substitutions", [])
    minutes = plan.get("minutes", {})

    # --- Check starting XI has correct slots ---
    xi_slots = set(xi.keys())
    if xi_slots != all_slot_names:
        missing = all_slot_names - xi_slots
        extra = xi_slots - all_slot_names
        if missing:
            errors.append(f"Starting XI missing slots: {sorted(missing)}")
        if extra:
            errors.append(f"Starting XI has unknown slots: {sorted(extra)}")

    # --- Check all players in XI + bench are known ---
    all_plan_players = set(xi.values()) | set(bench)
    all_known_players = set(players_by_name.keys())
    unknown = all_plan_players - all_known_players
    if unknown:
        errors.append(f"Unknown players in plan: {sorted(unknown)}")
    missing_players = all_known_players - all_plan_players
    if missing_players:
        errors.append(f"Players missing from plan entirely: {sorted(missing_players)}")

    # --- Check no player appears in both XI and bench ---
    xi_players = set(xi.values())
    bench_set = set(bench)
    overlap = xi_players & bench_set
    if overlap:
        errors.append(f"Players in both XI and bench: {sorted(overlap)}")

    # --- Check position compatibility for starting XI ---
    for slot_name, player_name in xi.items():
        if slot_name not in slot_type_map:
            continue  # already reported
        if player_name not in players_by_name:
            continue  # already reported
        stype = slot_type_map[slot_name]
        player = players_by_name[player_name]
        if not tree.player_can_fill_slot(player.positions, stype):
            errors.append(
                f"{player_name} cannot play {stype} (slot {slot_name}). "
                f"Their positions: {player.positions}"
            )

    # --- Check must_start / must_bench ---
    for p in players:
        if p.must_start and p.name not in xi_players:
            errors.append(f"{p.name} has must_start but is not in starting XI")
        if p.must_bench and p.name in xi_players:
            errors.append(f"{p.name} has must_bench but is in starting XI")

    # --- Simulate substitutions and check constraints at each point ---
    current_xi = dict(xi)
    current_bench = list(bench)
    prev_time = 0

    # Check never_bench_together at kickoff
    bench_names = set(current_bench)
    for pair in never_bench_together:
        if pair.issubset(bench_names):
            names = " & ".join(sorted(pair))
            errors.append(f"At kickoff: {names} are both on the bench (never_bench_together)")

    for sub_idx, sub in enumerate(subs):
        t = sub["time"]
        if t <= prev_time:
            errors.append(f"Substitution times not increasing: {t} <= {prev_time}")
        if t < 0 or t > duration:
            errors.append(f"Substitution time {t} is outside game duration (0-{duration})")

        for swap in sub.get("swaps", []):
            on_p = swap["on"]
            off_p = swap["off"]
            slot = swap["slot"]

            # Check off_p is currently in that slot
            if slot in current_xi and current_xi[slot] != off_p:
                errors.append(
                    f"At {t} min: {off_p} is supposed to come off from {slot}, "
                    f"but {current_xi.get(slot, '?')} is currently there"
                )

            # Check on_p is currently on the bench
            if on_p not in current_bench:
                errors.append(f"At {t} min: {on_p} is supposed to come on but is not on the bench")

            # Check position compatibility
            if slot in slot_type_map and on_p in players_by_name:
                stype = slot_type_map[slot]
                if not tree.player_can_fill_slot(players_by_name[on_p].positions, stype):
                    errors.append(
                        f"At {t} min: {on_p} cannot play {stype} (slot {slot}). "
                        f"Their positions: {players_by_name[on_p].positions}"
                    )

            # Perform the swap
            current_xi[slot] = on_p
            if on_p in current_bench:
                current_bench.remove(on_p)
            current_bench.append(off_p)

        # Check never_bench_together after this substitution window
        bench_names = set(current_bench)
        for pair in never_bench_together:
            if pair.issubset(bench_names):
                names = " & ".join(sorted(pair))
                errors.append(f"At {t} min: {names} are both on the bench (never_bench_together)")

        prev_time = t

    # --- Check minutes ---
    for player_name, info in minutes.items():
        if player_name not in players_by_name:
            continue
        p = players_by_name[player_name]
        total = info.get("total", 0)
        stints = info.get("stints", [])

        # Verify stints sum to total
        if sum(stints) != total:
            errors.append(f"{player_name}: stints {stints} sum to {sum(stints)}, not {total}")

        if total < p.min_minutes:
            errors.append(f"{player_name}: {total} min < min_minutes {p.min_minutes}")
        if total > p.max_minutes:
            errors.append(f"{player_name}: {total} min > max_minutes {p.max_minutes}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate plan against game constraints.")
    parser.add_argument("game_file", help="Path to game YAML config")
    parser.add_argument("plan_file", help="Path to plan YAML file")
    parser.add_argument("--plan", type=int, default=None, help="Validate only this plan number")
    args = parser.parse_args()

    try:
        game, players, tree = load_config(args.game_file)
    except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
        print(f"Error loading game config: {e}")
        sys.exit(1)

    try:
        with open(args.plan_file) as f:
            data = yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"Error loading plan file: {e}")
        sys.exit(1)

    plans = data.get("plans", [])
    if not plans:
        print("No plans found in plan file.")
        sys.exit(1)

    slots = tree.get_slots()
    all_passed = True

    if args.plan is not None:
        if args.plan < 1 or args.plan > len(plans):
            print(f"Error: plan {args.plan} not found (file has {len(plans)} plans).")
            sys.exit(1)
        plans_to_check = [(args.plan, plans[args.plan - 1])]
    else:
        plans_to_check = [(p["plan_number"], p) for p in plans]

    for plan_num, plan in plans_to_check:
        errors = validate_plan(plan, game, players, tree, slots)
        if errors:
            all_passed = False
            print(f"Plan {plan_num}: FAIL")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"Plan {plan_num}: PASS")

    if all_passed:
        print(f"\nAll {len(plans_to_check)} plan(s) passed validation.")
    else:
        print(f"\nSome plans failed validation.")
        sys.exit(1)


if __name__ == "__main__":
    main()
