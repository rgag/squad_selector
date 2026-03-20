# Hockey Match Substitution Planner

Generates substitution plans for a 70-minute field hockey match based on your
available players and their position/time constraints. The planner aims to
distribute playing time as evenly as possible across all players.

## Setup

```bash
sudo apt install python3-yaml
```

## Running

```bash
python hockey_planner.py game.yaml
```

This prints up to 5 plans. Each plan shows a starting lineup, when to make
substitutions, who swaps with whom, and the total minutes each player ends up
with. Pick whichever plan suits the game.

To generate more or fewer plans, change `num_plans` in the config, or use the
`--plans` flag:

```bash
python hockey_planner.py game.yaml --plans 3
```

---

## The config file (game.yaml)

Fill this in before each match. It has two sections: **game settings** and
**players**.

### Game settings

```yaml
game:
  duration: 70
  formation: "4-3-3"
  sub_windows:
    min: 2
    max: 4
  num_plans: 5
  constraints:
    never_bench_together: []
```

| Setting | What it means |
|---|---|
| `duration` | Length of the game in minutes |
| `formation` | How many defenders, midfielders, forwards (see below) |
| `sub_windows min` | Fewest substitution moments you want |
| `sub_windows max` | Most substitution moments you want |
| `num_plans` | How many alternative plans to generate |

### Players

```yaml
players:
  - name: Alice
    positions: [GK]
    min_minutes: 60
    max_minutes: 70
    must_start: true

  - name: Bob
    positions: [DEF, MID]
    min_minutes: 45
    max_minutes: 70

  - name: Charlie
    positions: [DEF]
    min_minutes: 0
    max_minutes: 40
    must_bench: true
```

| Field | What it means |
|---|---|
| `name` | Player's name (anything you like) |
| `positions` | Which positions this player can cover (see below) |
| `min_minutes` | Minimum playing time you want them to have |
| `max_minutes` | Maximum playing time — the planner will sub them off before this is exceeded |
| `must_start` | `true` to force this player into the starting XI |
| `must_bench` | `true` to force this player to start on the bench |

**Tips:**
- Set `min_minutes: 0` for a player who is happy to sit out entirely.
- Set `min_minutes` and `max_minutes` to the same value to lock a player to
  an exact amount of time (e.g. a keeper who plays the whole game: both set to `70`).
- List more than one position for versatile players, e.g. `positions: [DEF, MID]`.
  The planner will use them wherever they fit.

---

## Constraints

Add a `constraints` section under `game` for team-level rules:

```yaml
game:
  constraints:
    never_bench_together:
      - [Nick, George]
      - [Jess, Harry]
```

### `never_bench_together`

Each entry is a pair of player names. At least one of the two must be on the
pitch at all times — they cannot both sit on the bench simultaneously.

Useful for:
- Ensuring you always have an experienced player in a key position
- Keeping one of two strikers on the pitch at all times

You can have as many pairs as you like. Remove or leave the list empty if you
don't need any.

---

## Positions

You can use **broad** labels or **specific** labels. Broad labels match any
slot of that type, so `DEF` covers centre-back, left-back, etc.

### Broad labels (simplest — recommended for most players)

| Label | Covers |
|---|---|
| `GK` | Goalkeeper |
| `DEF` | Any defensive slot |
| `MID` | Any midfield slot |
| `FWD` | Any forward slot |

### Specific labels (optional — for specialists)

| Group | Labels |
|---|---|
| Goalkeeper | `GK` |
| Defenders | `CB`, `LB`, `RB`, `SW` |
| Midfielders | `CM`, `LM`, `RM`, `DM`, `AM` |
| Forwards | `CF`, `LW`, `RW` |

You can mix broad and specific in the same player's list, e.g.
`positions: [DM, FWD]`.

---

## Formations

The formation is written as **DEF-MID-FWD**. The goalkeeper is always included
automatically, so the three numbers must add up to **10**.

Any combination that totals 10 works. Common examples:

| Formation | Defenders | Midfielders | Forwards |
|---|---|---|---|
| `4-3-3` | 4 | 3 | 3 |
| `4-4-2` | 4 | 4 | 2 |
| `3-5-2` | 3 | 5 | 2 |
| `4-2-4` | 4 | 2 | 4 |
| `5-3-2` | 5 | 3 | 2 |
| `3-4-3` | 3 | 4 | 3 |

If the numbers don't add up to 10 you'll get an error message explaining why.

---

## Example output

```
=== PLAN 1 of 5 ===

Starting lineup:
  GK : Tadi
  D1 : George    D2 : Nick    D3 : Hayley
  M1 : Emily    M2 : Jess    M3 : Harry    M4 : Louisa    M5 : Zoe
  F1 : Daisy    F2 : Charlotte

  Bench: Izzy, Nicky

Substitution at 35 min (half time):
  Izzy ON (M4)  <->  Louisa OFF
  Nicky ON (M2)  <->  Jess OFF

Substitution at 41 min:
  Louisa ON (M5)  <->  Zoe OFF
  Jess ON (M1)  <->  Emily OFF

...

Minutes played:
  Charlotte: 54 + 3 = 57    Daisy: 48 + 16 = 64    Emily: 41 + 22 = 63
  George: 70                Harry: 48 + 10 = 58    Hayley: 70
  ...
```

Players who return via a rolling sub show their stints split out, e.g.
`Jess: 35 + 26 = 61`.
