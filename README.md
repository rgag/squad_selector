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
python hockey_planner.py game.yaml -o plan.yaml
```

This generates up to 5 plans and writes them to `plan.yaml` in YAML format.

To generate more or fewer plans, change `num_plans` in the config, or use the
`--plans` flag:

```bash
python hockey_planner.py game.yaml -o plan.yaml --plans 3
```

### Viewing plans

Convert the YAML output to human-readable text:

```bash
python format_plan.py plan.yaml           # show all plans
python format_plan.py plan.yaml --plan 2  # show only plan 2
```

### Validating plans

Check that a plan meets all the constraints in the game config:

```bash
python validate_plan.py game.yaml plan.yaml
```

---

## The config file (game.yaml)

Fill this in before each match. It has two sections: **game settings** and
**players**.

### Game settings

```yaml
game:
  duration: 70
  positions:
    DEF:
      FB:
        LB: 1
        RB: 1
      CB: 1
    MID:
      Wing:
        LM: 1
        RM: 1
      DM: 2
      AM: 1
    FWD:
      CF: 2
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
| `positions` | Nested structure defining the positions on the pitch (see below) |
| `sub_windows min` | Fewest substitution moments you want |
| `sub_windows max` | Most substitution moments you want |
| `num_plans` | How many alternative plans to generate |

### Positions

The `positions` block defines both the pitch slots **and** the position
hierarchy. It's a nested structure where:

- **Leaf nodes** (values are numbers) are actual pitch slots. The number is
  how many of that position you need.
- **Internal nodes** (values are nested dicts) are grouping labels used for
  player eligibility.

GK (goalkeeper) is always added automatically — you don't need to include it.

Example:

```yaml
positions:
  DEF:
    FB:
      LB: 1
      RB: 1
    CB: 1
  MID:
    Wing:
      LM: 1
      RM: 1
    DM: 2
    AM: 1
  FWD:
    CF: 2
```

This gives you: GK, LB, RB, CB, LM, RM, 2× DM, AM, 2× CF = 11 players.

The hierarchy means:
- A player with position `FB` can play LB or RB
- A player with position `DEF` can play LB, RB, or CB
- A player with position `MID` can play LM, RM, DM, AM, or Wing
- A player with position `FWD` can play CF

You define whatever positions and groupings make sense for your team — the
hierarchy is not fixed.

### Players

```yaml
players:
  - name: Alice
    positions: [GK]
    min_minutes: 60
    max_minutes: 70
    must_start: true

  - name: Bob
    positions: [DEF, DM]
    min_minutes: 45
    max_minutes: 70

  - name: Charlie
    positions: [CB]
    min_minutes: 0
    max_minutes: 40
    must_bench: true
```

| Field | What it means |
|---|---|
| `name` | Player's name (anything you like) |
| `positions` | Which positions this player can cover — can be leaf or group labels |
| `min_minutes` | Minimum playing time you want them to have |
| `max_minutes` | Maximum playing time — the planner will sub them off before this is exceeded |
| `must_start` | `true` to force this player into the starting XI |
| `must_bench` | `true` to force this player to start on the bench |

**Tips:**
- Set `min_minutes: 0` for a player who is happy to sit out entirely.
- Set `min_minutes` and `max_minutes` to the same value to lock a player to
  an exact amount of time (e.g. a keeper who plays the whole game: both set to `70`).
- Use group labels like `DEF` or `MID` for versatile players, and specific
  labels like `LB` or `DM` for specialists.

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

## Example output

```
python hockey_planner.py game.yaml -o plan.yaml
python format_plan.py plan.yaml --plan 1
```

```
=== PLAN 1 of 5 ===

Starting lineup:
  GK : Tadi
  CB : Hayley    CB : George    CB : Nick
  LM : Zoe
  RM : Izzy
  DM : Louisa    DM : Harry
  AM : Jess
  CF : Charlotte    CF : Emily

  Bench: Nicky, Daisy

Substitution at 18 min:
  Nicky ON (RM)  <->  Izzy OFF
  Daisy ON (CF)  <->  Charlotte OFF
  ...

Minutes played:
  Charlotte: 18 + 35 = 53    Daisy: 52               Emily: 35 + 18 = 53
  George: 70                 Harry: 35 + 18 = 53     Hayley: 70
  ...
```
