#!/usr/bin/env python3
"""Hockey Match Substitution Planner

Usage:
    python hockey_planner.py game.yaml -o plan.yaml
    python hockey_planner.py game.yaml -o plan.yaml --plans 3
"""

import sys
import argparse
import yaml
from dataclasses import dataclass
from typing import Optional
import random


# ---------------------------------------------------------------------------
# Position tree — built from the nested positions dict in game.yaml
# ---------------------------------------------------------------------------

class PositionTree:
    """Represents the hierarchical position structure.

    Built from a nested dict like:
        DEF:
          FB:
            LB: 1
            RB: 1
          CB: 1
        MID:
          DM: 2
          AM: 1
        FWD:
          CF: 2

    Leaf nodes (int values) are pitch slots. Internal nodes are grouping labels.
    GK is always added implicitly with count 1.
    """

    def __init__(self, positions_dict: dict):
        self.ancestors: dict[str, list[str]] = {}    # node -> [parent, grandparent, ...]
        self.descendants: dict[str, set[str]] = {}   # node -> set of leaf positions reachable
        self.leaf_counts: dict[str, int] = {}         # leaf_position -> count
        self.top_group: dict[str, str] = {}           # leaf_position -> top-level group name
        self.top_groups_ordered: list[str] = []       # top-level groups in definition order
        self.all_nodes: set[str] = set()              # every node name in the tree

        # Always add GK
        self.ancestors["GK"] = []
        self.descendants["GK"] = {"GK"}
        self.leaf_counts["GK"] = 1
        self.top_group["GK"] = "GK"
        self.top_groups_ordered.append("GK")
        self.all_nodes.add("GK")

        for top_key, top_val in positions_dict.items():
            self.top_groups_ordered.append(top_key)
            self.all_nodes.add(top_key)
            self.descendants[top_key] = set()
            if isinstance(top_val, int):
                # Top-level key is itself a leaf
                self.ancestors[top_key] = []
                self.leaf_counts[top_key] = top_val
                self.top_group[top_key] = top_key
                self.descendants[top_key].add(top_key)
            else:
                self.ancestors.setdefault(top_key, [])
                self._build(top_val, parent_chain=[top_key], top_group=top_key)

    def _build(self, node: dict, parent_chain: list[str], top_group: str):
        for key, val in node.items():
            self.all_nodes.add(key)
            self.ancestors[key] = list(parent_chain)
            if isinstance(val, int):
                # Leaf node
                self.leaf_counts[key] = val
                self.top_group[key] = top_group
                self.descendants[key] = {key}
                # Update all ancestors' descendant sets
                for ancestor in parent_chain:
                    self.descendants.setdefault(ancestor, set()).add(key)
            else:
                # Internal grouping node
                self.descendants[key] = set()
                self._build(val, parent_chain=[key] + parent_chain, top_group=top_group)
                # Propagate descendants upward
                for ancestor in parent_chain:
                    self.descendants.setdefault(ancestor, set()).update(self.descendants[key])

    def player_can_fill_slot(self, player_positions: list[str], slot_type: str) -> bool:
        """True if any of the player's positions is equal to or an ancestor of slot_type."""
        for pos in player_positions:
            if pos == slot_type:
                return True
            if pos in self.ancestors.get(slot_type, []):
                return True
        return False

    def get_reachable_leaves(self, positions: list[str]) -> set[str]:
        """Get all leaf positions reachable from the given position labels."""
        leaves = set()
        for pos in positions:
            if pos in self.descendants:
                leaves.update(self.descendants[pos])
            elif pos in self.leaf_counts:
                leaves.add(pos)
        return leaves

    def get_slots(self) -> list[dict]:
        """Return list of slot dicts: {"name": "DM1", "type": "DM", "top_group": "MID"}."""
        slots = []
        # Produce slots in top-group order, then by leaf definition order
        for top in self.top_groups_ordered:
            leaves_in_group = []
            if top in self.leaf_counts:
                leaves_in_group.append(top)
            else:
                self._collect_leaves_ordered(top, leaves_in_group)
            for leaf in leaves_in_group:
                count = self.leaf_counts[leaf]
                for i in range(1, count + 1):
                    name = f"{leaf}{i}" if count > 1 else leaf
                    slots.append({"name": name, "type": leaf, "top_group": self.top_group[leaf]})
        return slots

    def _collect_leaves_ordered(self, node: str, result: list[str]):
        """Collect leaf nodes under a node, preserving definition order."""
        # We need the original dict structure for ordering — use descendants as fallback
        # Since we lost ordering info, we'll track it during build. For now, use descendants.
        # Actually we need to walk the tree again. Let's store children order.
        pass

    def validate_player_position(self, pos: str) -> bool:
        """Check if a position label exists in the tree."""
        return pos in self.all_nodes


class PositionTreeOrdered(PositionTree):
    """PositionTree that also preserves definition order of leaves for slot generation."""

    def __init__(self, positions_dict: dict):
        self._ordered_leaves: list[str] = []
        self._leaves_by_group: dict[str, list[str]] = {}
        super().__init__(positions_dict)

    def _build(self, node: dict, parent_chain: list[str], top_group: str):
        for key, val in node.items():
            self.all_nodes.add(key)
            self.ancestors[key] = list(parent_chain)
            if isinstance(val, int):
                self.leaf_counts[key] = val
                self.top_group[key] = top_group
                self.descendants[key] = {key}
                self._ordered_leaves.append(key)
                self._leaves_by_group.setdefault(top_group, []).append(key)
                for ancestor in parent_chain:
                    self.descendants.setdefault(ancestor, set()).add(key)
            else:
                self.descendants[key] = set()
                self._build(val, parent_chain=[key] + parent_chain, top_group=top_group)
                for ancestor in parent_chain:
                    self.descendants.setdefault(ancestor, set()).update(self.descendants[key])

    def get_slots(self) -> list[dict]:
        slots = []
        # GK first
        slots.append({"name": "GK", "type": "GK", "top_group": "GK"})
        # Then in definition order
        for leaf in self._ordered_leaves:
            count = self.leaf_counts[leaf]
            for i in range(1, count + 1):
                name = f"{leaf}{i}" if count > 1 else leaf
                slots.append({"name": name, "type": leaf, "top_group": self.top_group[leaf]})
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
    must_start: bool = False
    must_bench: bool = False


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

def load_config(path: str) -> tuple[dict, list[Player], PositionTreeOrdered]:
    with open(path) as f:
        raw = yaml.safe_load(f)

    game = raw.get("game", {})
    game.setdefault("duration", 70)
    game.setdefault("sub_windows", {"min": 2, "max": 4})
    game.setdefault("num_plans", 5)

    if "formation" in game and "positions" not in game:
        raise ValueError(
            "The 'formation' field is no longer supported. "
            "Please replace it with a nested 'positions' block. "
            "See README.md for the new format."
        )

    if "positions" not in game:
        raise ValueError("game.positions is required. Define the pitch positions as a nested structure.")

    tree = PositionTreeOrdered(game["positions"])

    constraints = game.get("constraints") or {}
    raw_nbt = constraints.get("never_bench_together", [])
    if raw_nbt and isinstance(raw_nbt[0], str):
        game["never_bench_together"] = [frozenset(str(n) for n in raw_nbt)]
    else:
        game["never_bench_together"] = [frozenset(str(n) for n in pair) for pair in raw_nbt]

    players = []
    for p in raw.get("players", []):
        positions = [pos.upper() for pos in p["positions"]]
        # Validate positions against the tree
        for pos in positions:
            if not tree.validate_player_position(pos):
                raise ValueError(
                    f"Player '{p['name']}' has position '{pos}' which is not in the position tree. "
                    f"Valid positions: {sorted(tree.all_nodes)}"
                )
        players.append(Player(
            name=str(p["name"]),
            positions=positions,
            min_minutes=p.get("min_minutes", 0),
            max_minutes=p.get("max_minutes", game["duration"]),
            must_start=bool(p.get("must_start", False)),
            must_bench=bool(p.get("must_bench", False)),
        ))

    return game, players, tree


# ---------------------------------------------------------------------------
# Starting XI via two-phase backtracking
# ---------------------------------------------------------------------------

def find_starting_xi(
    slots: list[dict],
    player_order: list[Player],
    must_start_names: set[str],
    must_bench_names: set[str],
    never_bench_together: list[frozenset],
    tree: PositionTreeOrdered,
) -> Optional[dict[str, str]]:
    must_starters = [p for p in player_order if p.name in must_start_names]
    eligible = [p for p in player_order if p.name not in must_bench_names]

    assignment: dict[str, str] = {}
    used: set[str] = set()

    def place_must_start(idx: int) -> bool:
        if idx == len(must_starters):
            return True
        player = must_starters[idx]
        for slot in slots:
            if slot["name"] in assignment:
                continue
            if not tree.player_can_fill_slot(player.positions, slot["type"]):
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

    remaining_slots = [s for s in slots if s["name"] not in assignment]

    def fill_slots(idx: int) -> bool:
        if idx == len(remaining_slots):
            bench = {p.name for p in player_order if p.name not in assignment.values()}
            for pair in never_bench_together:
                if pair.issubset(bench):
                    return False
            return True
        slot = remaining_slots[idx]
        for player in eligible:
            if player.name in used:
                continue
            if not tree.player_can_fill_slot(player.positions, slot["type"]):
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
    tree: PositionTreeOrdered,
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
            slots, player_list, must_start_names, must_bench_names, never_bench_together, tree
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

    step = duration / (n_windows + 1)
    evenly = tuple(int(round(step * (i + 1))) for i in range(n_windows))
    if len(set(evenly)) == n_windows:
        timings_set.add(evenly)

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
    tree: PositionTreeOrdered,
) -> Optional[list[SubEvent]]:
    slot_to_player = dict(starting_xi)
    player_to_slot: dict[str, Optional[str]] = {v: k for k, v in starting_xi.items()}
    on_field = set(starting_xi.values())
    on_bench = list(bench_players)
    slot_type_map = {s["name"]: s["type"] for s in slots}

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
        max_swaps_this_window = len(on_bench)

        # --- 1. Forced off: player has reached their max_minutes ---
        for off_p in list(on_field):
            if len(swaps) >= max_swaps_this_window:
                break
            pdata = players_by_name[off_p]
            if pdata.max_minutes >= duration or cumulative[off_p] < pdata.max_minutes:
                continue
            slot = player_to_slot[off_p]
            candidate = _pick_sub_on(
                slot_type_map[slot], on_bench, cumulative,
                players_by_name, remaining, never_bench_together, off_p,
                [s[0] for s in swaps], tree,
            )
            if candidate is None:
                return None
            _do_swap(candidate, off_p, slot, on_field, on_bench, player_to_slot, slot_to_player, swaps, t)

        # --- 2. Opportunistic: bench player who still needs their minimum minutes ---
        for bp in list(on_bench):
            if len(swaps) >= max_swaps_this_window:
                break
            bpdata = players_by_name[bp]
            still_needed = bpdata.min_minutes - cumulative[bp]
            if still_needed <= 0 or still_needed > remaining:
                continue
            already_on_this_window = [s[0] for s in swaps]
            for off_p in sorted(on_field, key=lambda p: -cumulative[p]):
                if off_p in [s[1] for s in swaps] or off_p in already_on_this_window:
                    continue
                opdata = players_by_name[off_p]
                if remaining < opdata.min_minutes - cumulative[off_p]:
                    continue
                slot = player_to_slot[off_p]
                stype = slot_type_map[slot]
                if not tree.player_can_fill_slot(bpdata.positions, stype):
                    continue
                if cumulative[bp] + remaining > bpdata.max_minutes:
                    continue
                if would_violate_bench_together(off_p, bp, on_bench, never_bench_together):
                    continue
                _do_swap(bp, off_p, slot, on_field, on_bench, player_to_slot, slot_to_player, swaps, t)
                break

        # --- 3. Fairness rotation ---
        while len(swaps) < max_swaps_this_window:
            swap = _pick_fairness_swap(
                on_field, on_bench, cumulative, players_by_name,
                slot_type_map, player_to_slot, remaining,
                never_bench_together, tree,
                already_on=[s[0] for s in swaps],
                already_off=[s[1] for s in swaps],
            )
            if swap is None:
                break
            _do_swap(*swap, on_field, on_bench, player_to_slot, slot_to_player, swaps, t)

        if swaps:
            sub_events.append(SubEvent(time=t, swaps=swaps))

        prev_time = t

    for p in on_field:
        cumulative[p] += duration - prev_time

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
    remaining: int,
    never_bench_together: list,
    tree: PositionTreeOrdered,
    already_on: list,
    already_off: list,
) -> Optional[tuple[str, str, str]]:
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
            if cumulative[bp] >= cumulative[fp]:
                break
            fpdata = players_by_name[fp]
            if remaining < fpdata.min_minutes - cumulative[fp]:
                continue
            slot = player_to_slot[fp]
            stype = slot_type_map[slot]
            if not tree.player_can_fill_slot(bpdata.positions, stype):
                continue
            if would_violate_bench_together(fp, bp, on_bench, never_bench_together):
                continue
            return (bp, fp, slot)

    return None


def _pick_sub_on(
    slot_type: str,
    on_bench: list,
    cumulative: dict,
    players_by_name: dict,
    remaining: int,
    never_bench_together: list,
    going_off: str,
    already_on: list,
    tree: PositionTreeOrdered,
) -> Optional[str]:
    for bp in on_bench:
        if bp in already_on:
            continue
        bpdata = players_by_name[bp]
        if not tree.player_can_fill_slot(bpdata.positions, slot_type):
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
    tree: PositionTreeOrdered,
    num_plans: int = 5,
) -> list[Plan]:
    duration = game["duration"]
    win_min = game["sub_windows"]["min"]
    win_max = game["sub_windows"]["max"]
    never_bench_together = game.get("never_bench_together", [])

    slots = tree.get_slots()
    players_by_name = {p.name: p for p in players}

    n_slots = len(slots)
    if len(players) < n_slots:
        raise ValueError(f"You have {len(players)} players but need at least {n_slots}.")

    must_start_names = {p.name for p in players if p.must_start}
    must_bench_names = {p.name for p in players if p.must_bench}

    xi_options = find_diverse_starting_xis(
        slots, players, must_start_names, must_bench_names, never_bench_together, tree, limit=40
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
            if len(players) == n_slots:
                continue

            for timings in generate_window_timings(duration, n_windows):
                sub_events = generate_subs_for_windows(
                    timings, starting_xi, bench_names, slots,
                    players_by_name, duration, never_bench_together, tree,
                )
                if sub_events is None:
                    continue
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
# YAML output
# ---------------------------------------------------------------------------

def plans_to_yaml(plans: list[Plan], game: dict, config_path: str) -> dict:
    """Convert plans to a serializable dict for YAML output."""
    output = {
        "game_file": config_path,
        "duration": game["duration"],
        "num_plans": len(plans),
        "plans": [],
    }
    for i, plan in enumerate(plans, 1):
        plan_dict = {
            "plan_number": i,
            "score": round(plan.score, 2),
            "starting_xi": dict(plan.starting_xi),
            "bench": list(plan.bench),
            "substitutions": [],
            "minutes": {},
        }
        for ev in plan.sub_events:
            sub_dict = {
                "time": ev.time,
                "swaps": [
                    {"on": on_p, "off": off_p, "slot": slot}
                    for on_p, off_p, slot in ev.swaps
                ],
            }
            plan_dict["substitutions"].append(sub_dict)
        for name, stints in sorted(plan.minutes.items()):
            plan_dict["minutes"][name] = {
                "total": sum(stints),
                "stints": stints,
            }
        output["plans"].append(plan_dict)
    return output


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def diagnose_impossible(game: dict, players: list[Player], tree: PositionTreeOrdered) -> None:
    duration = game["duration"]
    slots = tree.get_slots()
    never_bench_together = game.get("never_bench_together", [])
    print("\nDiagnosing constraints...")

    for stype in set(s["type"] for s in slots):
        capable = [p for p in players if tree.player_can_fill_slot(p.positions, stype)]
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
    parser.add_argument("-o", "--output", required=True, help="Output YAML plan file")
    parser.add_argument("--plans", type=int, default=None, help="Override num_plans from config")
    args = parser.parse_args()

    try:
        game, players, tree = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: config file '{args.config}' not found.")
        sys.exit(1)
    except (yaml.YAMLError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.plans is not None:
        game["num_plans"] = args.plans

    num_plans = game["num_plans"]
    duration = game["duration"]
    slots = tree.get_slots()

    slot_summary = ", ".join(f"{s['type']}" for s in slots)
    print("Hockey Substitution Planner")
    print(f"  Positions : {slot_summary}")
    print(f"  Duration  : {duration} min")
    print(f"  Sub windows: {game['sub_windows']['min']}–{game['sub_windows']['max']}")
    print(f"  Players   : {len(players)}")
    print(f"  Generating up to {num_plans} plan(s)...\n")

    n_slots = len(slots)
    if len(players) == n_slots:
        print(f"Warning: exactly {n_slots} players — no bench available. Generating no-sub plan only.")
        must_start_names = {p.name for p in players if p.must_start}
        must_bench_names = {p.name for p in players if p.must_bench}
        never_bench_together = game.get("never_bench_together", [])
        xi = find_starting_xi(slots, players, must_start_names, must_bench_names, never_bench_together, tree)
        if xi is None:
            print("Error: could not build a valid starting lineup.")
            diagnose_impossible(game, players, tree)
            sys.exit(1)
        stints = {p: [duration] for p in xi.values()}
        plan = Plan(starting_xi=xi, bench=[], sub_events=[], minutes=stints)
        output = plans_to_yaml([plan], game, args.config)
        with open(args.output, "w") as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False)
        print(f"Wrote 1 plan to {args.output}")
        return

    try:
        plans = generate_plans(game, players, tree, num_plans=num_plans)
    except ValueError as e:
        print(f"Error: {e}")
        diagnose_impossible(game, players, tree)
        sys.exit(1)

    if not plans:
        print("No valid plans found. Your constraints may be too tight.")
        diagnose_impossible(game, players, tree)
        sys.exit(1)

    output = plans_to_yaml(plans, game, args.config)
    with open(args.output, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {len(plans)} plan(s). Written to {args.output}")


if __name__ == "__main__":
    main()
