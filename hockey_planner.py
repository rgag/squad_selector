#!/usr/bin/env python3
"""Hockey Match Substitution Planner

Usage:
    python hockey_planner.py game.yaml
    python hockey_planner.py game.yaml --plans 3
"""

import sys
import argparse
import yaml
from dataclasses import dataclass
from typing import Optional
import random


# ---------------------------------------------------------------------------
# Position compatibility
# ---------------------------------------------------------------------------

BROAD_TO_SPECIFICS = {
    "GK":  {"GK"},
    "DEF": {"DEF", "CB", "LB", "RB", "SW"},
    "MID": {"MID", "CM", "LM", "RM", "DM", "AM"},
    "FWD": {"FWD", "CF", "LW", "RW"},
}

LABEL_TO_BROAD = {}
for _broad, _specifics in BROAD_TO_SPECIFICS.items():
    for _s in _specifics:
        LABEL_TO_BROAD[_s] = _broad


def player_can_fill_slot(player_positions: list[str], slot_type: str) -> bool:
    slot_broad = LABEL_TO_BROAD.get(slot_type, slot_type)
    for pos in player_positions:
        pos_broad = LABEL_TO_BROAD.get(pos, pos)
        if pos_broad == slot_broad or pos == slot_type:
            return True
    return False


def positions_overlap(positions_a: list[str], positions_b: list[str], slot_broad_type: str) -> bool:
    """
    Return True if player A can replace player B (or vice versa) in a slot of slot_broad_type.

    Rules:
    - A broad label (e.g. MID) is compatible with any specific position of that type (DM, LM, etc.)
    - Two specific positions only match if they are identical (DM != LM)

    So: DM↔DM ✓  DM↔MID ✓  DM↔LM ✗  MID↔LM ✓
    """
    a_relevant = [p for p in positions_a if LABEL_TO_BROAD.get(p, p) == slot_broad_type]
    b_relevant = [p for p in positions_b if LABEL_TO_BROAD.get(p, p) == slot_broad_type]
    if not a_relevant or not b_relevant:
        return False
    for a_pos in a_relevant:
        for b_pos in b_relevant:
            if a_pos == b_pos:
                return True  # exact match (including both being the broad label)
            if a_pos == slot_broad_type or b_pos == slot_broad_type:
                return True  # one side has the broad label — compatible with anything
    return False


# ---------------------------------------------------------------------------
# Formation parsing
# ---------------------------------------------------------------------------

def parse_formation(formation: str, duration: int) -> list[dict]:
    parts = formation.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"Formation '{formation}' must be DEF-MID-FWD (e.g. '4-3-3')")
    try:
        n_def, n_mid, n_fwd = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        raise ValueError(f"Formation '{formation}' must contain integers only")
    total = 1 + n_def + n_mid + n_fwd
    if total != 11:
        raise ValueError(f"Formation '{formation}' gives {total} players (need 11)")
    slots = [{"name": "GK", "type": "GK"}]
    for i in range(1, n_def + 1):
        slots.append({"name": f"D{i}", "type": "DEF"})
    for i in range(1, n_mid + 1):
        slots.append({"name": f"M{i}", "type": "MID"})
    for i in range(1, n_fwd + 1):
        slots.append({"name": f"F{i}", "type": "FWD"})
    return slots


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Player:
    name: str
    positions: list[str]
    min_minutes: int
    max_minutes: int
    must_start: bool = False   # must be in the starting XI
    must_bench: bool = False   # must start on the bench


@dataclass
class SubEvent:
    time: int
    swaps: list[tuple[str, str, str]]  # (on_player, off_player, slot_name)


@dataclass
class Plan:
    starting_xi: dict[str, str]   # slot_name -> player_name
    bench: list[str]
    sub_events: list[SubEvent]
    minutes: dict[str, list[int]]  # player_name -> list of stint lengths
    score: float = 0.0


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: str) -> tuple[dict, list[Player]]:
    with open(path) as f:
        raw = yaml.safe_load(f)

    game = raw.get("game", {})
    game.setdefault("duration", 70)
    game.setdefault("formation", "4-3-3")
    game.setdefault("sub_windows", {"min": 2, "max": 4})
    game.setdefault("num_plans", 5)

    constraints = game.get("constraints", {})
    raw_nbt = constraints.get("never_bench_together", [])
    if raw_nbt and isinstance(raw_nbt[0], str):
        # Single pair written as a flat list: [Harry, Louisa]
        game["never_bench_together"] = [frozenset(str(n) for n in raw_nbt)]
    else:
        # List of pairs: [[Harry, Louisa], [Charlotte, Daisy]]
        game["never_bench_together"] = [frozenset(str(n) for n in pair) for pair in raw_nbt]

    players = []
    for p in raw.get("players", []):
        players.append(Player(
            name=str(p["name"]),
            positions=[pos.upper() for pos in p["positions"]],
            min_minutes=p.get("min_minutes", 0),
            max_minutes=p.get("max_minutes", game["duration"]),
            must_start=bool(p.get("must_start", False)),
            must_bench=bool(p.get("must_bench", False)),
        ))

    return game, players


# ---------------------------------------------------------------------------
# Starting XI via two-phase backtracking
# ---------------------------------------------------------------------------

def find_starting_xi(
    slots: list[dict],
    player_order: list[Player],
    must_start_names: set[str],
    must_bench_names: set[str],
    never_bench_together: list[frozenset],
) -> Optional[dict[str, str]]:
    """
    Two-phase backtracking:
      Phase 1 — place must_start players into slots.
      Phase 2 — fill remaining slots from eligible (non-must_bench) players.
    Then verify never_bench_together: for each pair, at least one must be in the XI.
    """
    must_starters = [p for p in player_order if p.name in must_start_names]
    eligible = [p for p in player_order if p.name not in must_bench_names]

    assignment: dict[str, str] = {}
    used: set[str] = set()

    # Phase 1: place must_start players
    def place_must_start(idx: int) -> bool:
        if idx == len(must_starters):
            return True
        player = must_starters[idx]
        for slot in slots:
            if slot["name"] in assignment:
                continue
            if not player_can_fill_slot(player.positions, slot["type"]):
                continue
            assignment[slot["name"]] = player.name
            used.add(player.name)
            if place_must_start(idx + 1):
                return True
            del assignment[slot["name"]]
            used.remove(player.name)
        return False

    if must_starters and not place_must_start(0):
        return None

    # Phase 2: fill remaining slots
    remaining_slots = [s for s in slots if s["name"] not in assignment]

    def fill_slots(idx: int) -> bool:
        if idx == len(remaining_slots):
            # Check never_bench_together: no pair may both be on the bench
            bench = {p.name for p in player_order if p.name not in assignment.values()}
            for pair in never_bench_together:
                if pair.issubset(bench):
                    return False
            return True
        slot = remaining_slots[idx]
        for player in eligible:
            if player.name in used:
                continue
            if not player_can_fill_slot(player.positions, slot["type"]):
                continue
            assignment[slot["name"]] = player.name
            used.add(player.name)
            if fill_slots(idx + 1):
                return True
            del assignment[slot["name"]]
            used.remove(player.name)
        return False

    if fill_slots(0):
        return dict(assignment)
    return None


def find_diverse_starting_xis(
    slots: list[dict],
    players: list[Player],
    must_start_names: set[str],
    must_bench_names: set[str],
    never_bench_together: list[frozenset],
    limit: int = 40,
) -> list[dict[str, str]]:
    results = []
    seen_benches: set[frozenset] = set()
    player_list = list(players)

    random.seed(42)
    for _ in range(300):
        if len(results) >= limit:
            break
        random.shuffle(player_list)
        xi = find_starting_xi(
            slots, player_list, must_start_names, must_bench_names, never_bench_together
        )
        if xi is None:
            continue
        bench = frozenset(p.name for p in players if p.name not in xi.values())
        if bench in seen_benches:
            continue
        seen_benches.add(bench)
        results.append(xi)

    return results


# ---------------------------------------------------------------------------
# Sub window timing generation
# ---------------------------------------------------------------------------

def generate_window_timings(duration: int, n_windows: int) -> list[list[int]]:
    timings_set: set[tuple] = set()

    # Evenly spaced across the whole game
    step = duration / (n_windows + 1)
    evenly = tuple(int(round(step * (i + 1))) for i in range(n_windows))
    if len(set(evenly)) == n_windows:
        timings_set.add(evenly)

    # Half-time aligned: one window at 35, remaining distributed evenly either side
    half = duration // 2
    if n_windows == 1:
        timings_set.add((half,))
    elif n_windows >= 2:
        n_first = n_windows // 2
        n_second = n_windows - n_first
        first_step = half / (n_first + 1)
        second_step = (duration - half) / (n_second + 1)
        first_half = tuple(int(round(first_step * (i + 1))) for i in range(n_first))
        second_half = tuple(int(round(half + second_step * (i + 1))) for i in range(n_second))
        with_half = tuple(sorted(first_half + second_half))
        if len(set(with_half)) == n_windows:
            timings_set.add(with_half)

    # Offset variants of evenly-spaced
    base = list(evenly)
    for offset in [-5, -3, 3, 5]:
        candidate = tuple(max(1, min(duration - 1, t + offset)) for t in base)
        if len(set(candidate)) == n_windows:
            timings_set.add(candidate)

    return [list(t) for t in timings_set]


# ---------------------------------------------------------------------------
# Minutes computation
# ---------------------------------------------------------------------------

def compute_minutes(
    starting_xi: dict[str, str],
    sub_events: list[SubEvent],
    duration: int,
    all_player_names: list[str],
) -> dict[str, list[int]]:
    stints: dict[str, list[int]] = {p: [] for p in all_player_names}
    stint_start: dict[str, Optional[int]] = {}
    on_field = set(starting_xi.values())
    for p in on_field:
        stint_start[p] = 0
    for p in all_player_names:
        if p not in stint_start:
            stint_start[p] = None

    for ev in sub_events:
        t = ev.time
        for on_p, off_p, _ in ev.swaps:
            if stint_start.get(off_p) is not None:
                elapsed = t - stint_start[off_p]
                if elapsed > 0:
                    stints[off_p].append(elapsed)
                stint_start[off_p] = None
            on_field.discard(off_p)
            on_field.add(on_p)
            stint_start[on_p] = t

    for p in on_field:
        if stint_start.get(p) is not None:
            remaining = duration - stint_start[p]
            if remaining > 0:
                stints[p].append(remaining)

    return stints


# ---------------------------------------------------------------------------
# Constraint helpers
# ---------------------------------------------------------------------------

def would_violate_bench_together(
    going_off: str,
    going_on: Optional[str],
    on_bench: list[str],
    never_bench_together: list[frozenset],
) -> bool:
    """Return True if sending going_off to bench (while going_on leaves bench) violates a constraint."""
    new_bench = (set(on_bench) | {going_off}) - ({going_on} if going_on else set())
    return any(pair.issubset(new_bench) for pair in never_bench_together)


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

def generate_subs_for_windows(
    timings: list[int],
    starting_xi: dict[str, str],
    bench_players: list[str],
    slots: list[dict],
    players_by_name: dict[str, Player],
    duration: int,
    never_bench_together: list[frozenset],
) -> Optional[list[SubEvent]]:
    slot_to_player = dict(starting_xi)
    player_to_slot: dict[str, Optional[str]] = {v: k for k, v in starting_xi.items()}
    on_field = set(starting_xi.values())
    on_bench = list(bench_players)
    slot_type_map = {s["name"]: s["type"] for s in slots}

    # Lock each slot's position requirement to whoever started there.
    # E.g. if a DM starts in M3, M3 always requires a DM — even after a sub.
    slot_required_positions: dict[str, list[str]] = {}
    for slot_name, player_name in starting_xi.items():
        broad = slot_type_map[slot_name]
        relevant = [p for p in players_by_name[player_name].positions
                    if LABEL_TO_BROAD.get(p, p) == broad]
        slot_required_positions[slot_name] = relevant if relevant else [broad]

    for p in on_bench:
        player_to_slot[p] = None

    cumulative: dict[str, int] = {p: 0 for p in players_by_name}
    sub_events: list[SubEvent] = []
    prev_time = 0

    for t in timings:
        elapsed = t - prev_time
        for p in on_field:
            cumulative[p] += elapsed

        swaps: list[tuple[str, str, str]] = []
        remaining = duration - t
        # Can't make more swaps than there are bench players at this moment
        max_swaps_this_window = len(on_bench)

        # --- 1. Forced off: player has reached their max_minutes ---
        for off_p in list(on_field):
            if len(swaps) >= max_swaps_this_window:
                break
            pdata = players_by_name[off_p]
            if pdata.max_minutes >= duration or cumulative[off_p] < pdata.max_minutes:
                continue
            slot = player_to_slot[off_p]
            stype = slot_type_map[slot]
            candidate = _pick_sub_on(
                slot_required_positions[slot], stype, on_bench, cumulative,
                players_by_name, remaining, never_bench_together, off_p,
                [s[0] for s in swaps],
            )
            if candidate is None:
                return None  # can't cover this slot — plan is invalid
            _do_swap(candidate, off_p, slot, on_field, on_bench, player_to_slot, slot_to_player, swaps, t)

        # --- 2. Opportunistic: bench player who still needs their minimum minutes ---
        for bp in list(on_bench):
            if len(swaps) >= max_swaps_this_window:
                break
            bpdata = players_by_name[bp]
            still_needed = bpdata.min_minutes - cumulative[bp]
            if still_needed <= 0 or still_needed > remaining:
                continue
            # Find the field player with the most accumulated time who can be replaced
            already_on_this_window = [s[0] for s in swaps]
            for off_p in sorted(on_field, key=lambda p: -cumulative[p]):
                if off_p in [s[1] for s in swaps] or off_p in already_on_this_window:
                    continue
                opdata = players_by_name[off_p]
                # Allow subbing off early if there's still enough game time to meet their min
                if remaining < opdata.min_minutes - cumulative[off_p]:
                    continue
                slot = player_to_slot[off_p]
                stype = slot_type_map[slot]
                if not positions_overlap(bpdata.positions, slot_required_positions[slot], stype):
                    continue
                if cumulative[bp] + remaining > bpdata.max_minutes:
                    continue
                if would_violate_bench_together(off_p, bp, on_bench, never_bench_together):
                    continue
                _do_swap(bp, off_p, slot, on_field, on_bench, player_to_slot, slot_to_player, swaps, t)
                break

        # --- 3. Fairness rotation: even out playing time ---
        # Bring on the bench player with least time, rest the field player with most time.
        # Repeat until we've made as many swaps as makes sense for this window.
        while len(swaps) < max_swaps_this_window:
            swap = _pick_fairness_swap(
                on_field, on_bench, cumulative, players_by_name,
                slot_type_map, player_to_slot, slot_required_positions, remaining,
                never_bench_together,
                already_on=[s[0] for s in swaps],
                already_off=[s[1] for s in swaps],
            )
            if swap is None:
                break
            _do_swap(*swap, on_field, on_bench, player_to_slot, slot_to_player, swaps, t)

        if swaps:
            sub_events.append(SubEvent(time=t, swaps=swaps))

        prev_time = t

    # Accumulate final time block
    for p in on_field:
        cumulative[p] += duration - prev_time

    # Validate all player min/max constraints
    for pname, pdata in players_by_name.items():
        total = cumulative[pname]
        if total < pdata.min_minutes or total > pdata.max_minutes:
            return None

    return sub_events


def _pick_fairness_swap(
    on_field: set,
    on_bench: list,
    cumulative: dict,
    players_by_name: dict,
    slot_type_map: dict,
    player_to_slot: dict,
    slot_required_positions: dict,
    remaining: int,
    never_bench_together: list,
    already_on: list,
    already_off: list,
) -> Optional[tuple[str, str, str]]:
    """
    Find the swap that most improves time equity:
    bench player with least time replaces field player with most time,
    subject to position compatibility and min/max constraints.
    Position compatibility is checked against the slot's original (starting) requirement.
    """
    bench_sorted = sorted(
        [bp for bp in on_bench if bp not in already_on],
        key=lambda p: cumulative[p],
    )
    for bp in bench_sorted:
        bpdata = players_by_name[bp]
        if remaining <= 0:
            break
        if cumulative[bp] + remaining > bpdata.max_minutes:
            continue

        field_sorted = sorted(
            [fp for fp in on_field if fp not in already_off and fp not in already_on],
            key=lambda p: -cumulative[p],
        )
        for fp in field_sorted:
            # Only swap if it actually improves fairness
            if cumulative[bp] >= cumulative[fp]:
                break  # field players only get less time from here — no improvement possible
            fpdata = players_by_name[fp]
            # Allow subbing off early if there's still enough game time to meet their min
            if remaining < fpdata.min_minutes - cumulative[fp]:
                continue
            slot = player_to_slot[fp]
            stype = slot_type_map[slot]
            if not positions_overlap(bpdata.positions, slot_required_positions[slot], stype):
                continue
            if would_violate_bench_together(fp, bp, on_bench, never_bench_together):
                continue
            return (bp, fp, slot)

    return None


def _pick_sub_on(
    required_positions: list[str],
    stype: str,
    on_bench: list,
    cumulative: dict,
    players_by_name: dict,
    remaining: int,
    never_bench_together: list,
    going_off: str,
    already_on: list,
) -> Optional[str]:
    for bp in on_bench:
        if bp in already_on:
            continue
        bpdata = players_by_name[bp]
        if not positions_overlap(bpdata.positions, required_positions, stype):
            continue
        if cumulative[bp] + remaining > bpdata.max_minutes:
            continue
        if would_violate_bench_together(going_off, bp, on_bench, never_bench_together):
            continue
        return bp
    return None


def _do_swap(
    on_p: str, off_p: str, slot: str,
    on_field: set, on_bench: list,
    player_to_slot: dict, slot_to_player: dict,
    swaps: list, t: int,
):
    on_bench.remove(on_p)
    on_bench.append(off_p)
    on_field.discard(off_p)
    on_field.add(on_p)
    player_to_slot[on_p] = slot
    player_to_slot[off_p] = None
    slot_to_player[slot] = on_p
    swaps.append((on_p, off_p, slot))


def score_plan(stints: dict[str, list[int]], players: list[Player]) -> float:
    """Score by how evenly playing time is distributed. Higher = better (less variance)."""
    totals = [sum(v) for v in stints.values()]
    if not totals:
        return 0.0
    mean = sum(totals) / len(totals)
    variance = sum((t - mean) ** 2 for t in totals) / len(totals)
    return -variance


# ---------------------------------------------------------------------------
# Main plan generator
# ---------------------------------------------------------------------------

def generate_plans(
    game: dict,
    players: list[Player],
    num_plans: int = 5,
) -> list[Plan]:
    duration = game["duration"]
    formation = game["formation"]
    win_min = game["sub_windows"]["min"]
    win_max = game["sub_windows"]["max"]
    never_bench_together = game.get("never_bench_together", [])

    slots = parse_formation(formation, duration)
    players_by_name = {p.name: p for p in players}

    if len(players) < 11:
        raise ValueError(f"You have {len(players)} players but need at least 11.")

    must_start_names = {p.name for p in players if p.must_start}
    must_bench_names = {p.name for p in players if p.must_bench}

    xi_options = find_diverse_starting_xis(
        slots, players, must_start_names, must_bench_names, never_bench_together, limit=40
    )
    if not xi_options:
        raise ValueError(
            "No valid starting lineup found. Check that positions cover all formation slots, "
            "and that must_start/must_bench/never_bench_together constraints are satisfiable."
        )

    plans: list[Plan] = []
    seen_sigs: set = set()

    for starting_xi in xi_options:
        bench_names = [p.name for p in players if p.name not in starting_xi.values()]

        for n_windows in range(win_min, win_max + 1):
            if len(players) == 11:
                continue

            for timings in generate_window_timings(duration, n_windows):
                sub_events = generate_subs_for_windows(
                    timings, starting_xi, bench_names, slots,
                    players_by_name, duration, never_bench_together,
                )
                if sub_events is None:
                    continue
                # Enforce the minimum number of actual substitution windows
                if len(sub_events) < win_min:
                    continue

                stints = compute_minutes(
                    starting_xi, sub_events, duration, [p.name for p in players]
                )

                sig = (
                    tuple(sorted(starting_xi.items())),
                    tuple((e.time, tuple(sorted(e.swaps))) for e in sub_events),
                )
                if sig in seen_sigs:
                    continue
                seen_sigs.add(sig)

                plans.append(Plan(
                    starting_xi=starting_xi,
                    bench=bench_names,
                    sub_events=sub_events,
                    minutes=stints,
                    score=score_plan(stints, players),
                ))

    plans.sort(key=lambda p: p.score, reverse=True)
    return plans[:num_plans]


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def display_position(player_name: str, slot_broad_type: str, players_by_name: dict) -> str:
    """Return the player's first listed position that matches the slot's broad type."""
    for pos in players_by_name[player_name].positions:
        if LABEL_TO_BROAD.get(pos, pos) == slot_broad_type:
            return pos
    return slot_broad_type  # fallback (shouldn't happen in a valid lineup)


def format_lineup(xi: dict[str, str], slots: list[dict], slot_label: dict[str, str]) -> str:
    lines = []
    rows: dict[str, list[str]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for slot in slots:
        rows[slot["type"]].append(f"  {slot_label[slot['name']]:3s}: {xi[slot['name']]}")
    for entries in rows.values():
        if entries:
            lines.append("  ".join(entries))
    return "\n".join(lines)


def format_minutes(stints: dict[str, list[int]]) -> str:
    items = []
    for name, s in sorted(stints.items()):
        if not s:
            items.append(f"  {name}: 0")
        elif len(s) == 1:
            items.append(f"  {name}: {s[0]}")
        else:
            expr = " + ".join(str(x) for x in s)
            items.append(f"  {name}: {expr} = {sum(s)}")
    col_width = max((len(i) for i in items), default=20) + 2
    lines = []
    for i in range(0, len(items), 3):
        lines.append("".join(item.ljust(col_width) for item in items[i:i + 3]))
    return "\n".join(lines)


def print_plan(plan: Plan, plan_num: int, total: int, slots: list[dict], players_by_name: dict) -> None:
    # Derive each slot's position label from whoever started there — fixed for the whole game.
    # This ensures "2x DM at kickoff" stays "2x DM" in every lineup shown.
    slot_label = {
        slot["name"]: display_position(plan.starting_xi[slot["name"]], slot["type"], players_by_name)
        for slot in slots
    }
    print(f"\n{'=' * 50}")
    print(f"=== PLAN {plan_num} of {total} ===")
    print(f"{'=' * 50}")
    print("\nStarting lineup:")
    print(format_lineup(plan.starting_xi, slots, slot_label))
    print(f"\n  Bench: {', '.join(plan.bench) if plan.bench else '(none)'}")
    if not plan.sub_events:
        print("\n  No substitutions.")
    else:
        current_xi = dict(plan.starting_xi)
        current_bench = list(plan.bench)
        for ev in plan.sub_events:
            half_note = " (half time)" if ev.time == 35 else ""
            print(f"\nSubstitution at {ev.time} min{half_note}:")
            for on_p, off_p, slot_name in ev.swaps:
                print(f"  {on_p} ON ({slot_label[slot_name]})  <->  {off_p} OFF")
                current_xi[slot_name] = on_p
                current_bench.remove(on_p)
                current_bench.append(off_p)
            print(format_lineup(current_xi, slots, slot_label))
            print(f"  Bench: {', '.join(current_bench)}")
    print("\nMinutes played:")
    print(format_minutes(plan.minutes))


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def diagnose_impossible(game: dict, players: list[Player]) -> None:
    duration = game["duration"]
    slots = parse_formation(game["formation"], duration)
    never_bench_together = game.get("never_bench_together", [])
    print("\nDiagnosing constraints...")

    for stype in set(s["type"] for s in slots):
        capable = [p for p in players if player_can_fill_slot(p.positions, stype)]
        needed = sum(1 for s in slots if s["type"] == stype)
        if len(capable) < needed:
            print(f"  IMPOSSIBLE: {stype} needs {needed} players, only {len(capable)} are eligible.")

    for p in players:
        if p.must_start and p.must_bench:
            print(f"  IMPOSSIBLE: {p.name} has both must_start and must_bench set.")
        if p.min_minutes > p.max_minutes:
            print(f"  IMPOSSIBLE: {p.name} min_minutes > max_minutes.")
        if p.min_minutes > duration:
            print(f"  IMPOSSIBLE: {p.name} min_minutes ({p.min_minutes}) > game duration ({duration}).")

    must_bench_names = {p.name for p in players if p.must_bench}
    for pair in never_bench_together:
        if pair.issubset(must_bench_names):
            names = " and ".join(pair)
            print(f"  IMPOSSIBLE: {names} are both must_bench but also in never_bench_together.")
        for name in pair:
            if name in must_bench_names:
                partner = next(n for n in pair if n != name)
                print(
                    f"  WARNING: {name} has must_bench=true and is in never_bench_together "
                    f"with {partner}. This means {partner} must play the full game."
                )

    total_min = sum(p.min_minutes for p in players)
    max_available = duration * len(slots)
    if total_min > max_available:
        print(
            f"  IMPOSSIBLE: Players require {total_min} combined minutes; "
            f"only {max_available} slot-minutes are available."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Hockey substitution planner.")
    parser.add_argument("config", help="Path to game YAML config file")
    parser.add_argument("--plans", type=int, default=None, help="Override num_plans from config")
    args = parser.parse_args()

    try:
        game, players = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: config file '{args.config}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error reading YAML: {e}")
        sys.exit(1)

    if args.plans is not None:
        game["num_plans"] = args.plans

    num_plans = game["num_plans"]
    duration = game["duration"]
    formation = game["formation"]

    print("Hockey Substitution Planner")
    print(f"  Formation : {formation}")
    print(f"  Duration  : {duration} min")
    print(f"  Sub windows: {game['sub_windows']['min']}–{game['sub_windows']['max']}")
    print(f"  Players   : {len(players)}")
    print(f"  Generating up to {num_plans} plan(s)...\n")

    try:
        slots = parse_formation(formation, duration)
    except ValueError as e:
        print(f"Formation error: {e}")
        sys.exit(1)

    must_start_names = {p.name for p in players if p.must_start}
    must_bench_names = {p.name for p in players if p.must_bench}
    never_bench_together = game.get("never_bench_together", [])

    if len(players) == 11:
        print("Warning: exactly 11 players — no bench available. Generating no-sub plan only.")
        xi = find_starting_xi(slots, players, must_start_names, must_bench_names, never_bench_together)
        if xi is None:
            print("Error: could not build a valid starting lineup.")
            diagnose_impossible(game, players)
            sys.exit(1)
        stints = {p: [duration] for p in xi.values()}
        plan = Plan(starting_xi=xi, bench=[], sub_events=[], minutes=stints)
        players_by_name = {p.name: p for p in players}
        print_plan(plan, 1, 1, slots, players_by_name)
        return

    try:
        plans = generate_plans(game, players, num_plans=num_plans)
    except ValueError as e:
        print(f"Error: {e}")
        diagnose_impossible(game, players)
        sys.exit(1)

    if not plans:
        print("No valid plans found. Your constraints may be too tight.")
        diagnose_impossible(game, players)
        sys.exit(1)

    players_by_name = {p.name: p for p in players}
    for i, plan in enumerate(plans, 1):
        print_plan(plan, i, len(plans), slots, players_by_name)

    print(f"\n{'=' * 50}")
    print(f"Generated {len(plans)} plan(s).")


if __name__ == "__main__":
    main()
