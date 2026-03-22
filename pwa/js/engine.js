// Hockey Substitution Planner Engine
// Ported from hockey_planner.py

// --- Seeded PRNG (mulberry32) ---
function mulberry32(seed) {
  return function() {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

function shuffleArray(arr, rng) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// --- Set helpers ---
function isSubset(small, big) {
  for (const item of small) {
    if (!big.has(item)) return false;
  }
  return true;
}

function setsIntersect(a, b) {
  for (const item of a) {
    if (b.has(item)) return true;
  }
  return false;
}

// --- Pair key for never_bench_together ---
function pairKey(pair) {
  return [...pair].sort().join('|');
}

// --- PositionTree ---
export class PositionTree {
  constructor(positionsDict) {
    this.ancestors = {};      // node -> [parent, grandparent, ...]
    this.descendants = {};    // node -> Set of leaf positions
    this.leafCounts = {};     // leaf -> count
    this.topGroup = {};       // leaf -> top-level group name
    this.topGroupsOrdered = [];
    this.allNodes = new Set();
    this._orderedLeaves = [];

    // Always add GK
    this.ancestors['GK'] = [];
    this.descendants['GK'] = new Set(['GK']);
    this.leafCounts['GK'] = 1;
    this.topGroup['GK'] = 'GK';
    this.topGroupsOrdered.push('GK');
    this.allNodes.add('GK');

    for (const topKey of Object.keys(positionsDict)) {
      this.topGroupsOrdered.push(topKey);
      this.allNodes.add(topKey);
      this.descendants[topKey] = new Set();
      const topVal = positionsDict[topKey];
      if (typeof topVal === 'number') {
        this.ancestors[topKey] = [];
        this.leafCounts[topKey] = topVal;
        this.topGroup[topKey] = topKey;
        this.descendants[topKey].add(topKey);
        this._orderedLeaves.push(topKey);
      } else {
        if (!this.ancestors[topKey]) this.ancestors[topKey] = [];
        this._build(topVal, [topKey], topKey);
      }
    }
  }

  _build(node, parentChain, topGroupName) {
    for (const key of Object.keys(node)) {
      const val = node[key];
      this.allNodes.add(key);
      this.ancestors[key] = [...parentChain];
      if (typeof val === 'number') {
        this.leafCounts[key] = val;
        this.topGroup[key] = topGroupName;
        this.descendants[key] = new Set([key]);
        this._orderedLeaves.push(key);
        for (const ancestor of parentChain) {
          if (!this.descendants[ancestor]) this.descendants[ancestor] = new Set();
          this.descendants[ancestor].add(key);
        }
      } else {
        this.descendants[key] = new Set();
        this._build(val, [key, ...parentChain], topGroupName);
        for (const ancestor of parentChain) {
          if (!this.descendants[ancestor]) this.descendants[ancestor] = new Set();
          for (const d of this.descendants[key]) {
            this.descendants[ancestor].add(d);
          }
        }
      }
    }
  }

  playerCanFillSlot(playerPositions, slotType) {
    for (const pos of playerPositions) {
      if (pos === slotType) return true;
      if (this.ancestors[slotType] && this.ancestors[slotType].includes(pos)) return true;
    }
    return false;
  }

  getReachableLeaves(positions) {
    const leaves = new Set();
    for (const pos of positions) {
      if (this.descendants[pos]) {
        for (const d of this.descendants[pos]) leaves.add(d);
      } else if (this.leafCounts[pos] !== undefined) {
        leaves.add(pos);
      }
    }
    return leaves;
  }

  getSlots() {
    const slots = [];
    slots.push({ name: 'GK', type: 'GK', topGroup: 'GK' });
    for (const leaf of this._orderedLeaves) {
      const count = this.leafCounts[leaf];
      for (let i = 1; i <= count; i++) {
        const name = count > 1 ? `${leaf}${i}` : leaf;
        slots.push({ name, type: leaf, topGroup: this.topGroup[leaf] });
      }
    }
    return slots;
  }

  validatePosition(pos) {
    return this.allNodes.has(pos);
  }
}

// --- Starting XI via backtracking ---
function findStartingXi(slots, playerOrder, mustStartNames, mustBenchNames, neverBenchTogether, tree) {
  const mustStarters = playerOrder.filter(p => mustStartNames.has(p.name));
  const eligible = playerOrder.filter(p => !mustBenchNames.has(p.name));
  const assignment = {};
  const used = new Set();

  function placeMustStart(idx) {
    if (idx === mustStarters.length) return true;
    const player = mustStarters[idx];
    for (const slot of slots) {
      if (assignment[slot.name] !== undefined) continue;
      if (!tree.playerCanFillSlot(player.positions, slot.type)) continue;
      assignment[slot.name] = player.name;
      used.add(player.name);
      if (placeMustStart(idx + 1)) return true;
      delete assignment[slot.name];
      used.delete(player.name);
    }
    return false;
  }

  if (mustStarters.length > 0 && !placeMustStart(0)) return null;

  const remainingSlots = slots.filter(s => assignment[s.name] === undefined);

  function fillSlots(idx) {
    if (idx === remainingSlots.length) {
      const bench = new Set(playerOrder.map(p => p.name).filter(n => !Object.values(assignment).includes(n)));
      for (const pair of neverBenchTogether) {
        if (isSubset(pair, bench)) return false;
      }
      return true;
    }
    const slot = remainingSlots[idx];
    for (const player of eligible) {
      if (used.has(player.name)) continue;
      if (!tree.playerCanFillSlot(player.positions, slot.type)) continue;
      assignment[slot.name] = player.name;
      used.add(player.name);
      if (fillSlots(idx + 1)) return true;
      delete assignment[slot.name];
      used.delete(player.name);
    }
    return false;
  }

  if (fillSlots(0)) return { ...assignment };
  return null;
}

function findDiverseStartingXis(slots, players, mustStartNames, mustBenchNames, neverBenchTogether, tree, limit = 40) {
  const results = [];
  const seenBenches = new Set();
  const rng = mulberry32(42);

  for (let i = 0; i < 300; i++) {
    if (results.length >= limit) break;
    const playerList = shuffleArray(players, rng);
    const xi = findStartingXi(slots, playerList, mustStartNames, mustBenchNames, neverBenchTogether, tree);
    if (!xi) continue;
    const xiValues = new Set(Object.values(xi));
    const benchKey = players.filter(p => !xiValues.has(p.name)).map(p => p.name).sort().join(',');
    if (seenBenches.has(benchKey)) continue;
    seenBenches.add(benchKey);
    results.push(xi);
  }
  return results;
}

// --- Sub window timing ---
function generateWindowTimings(duration, nWindows, equalPeriods = false) {
  const timingsSet = new Map();

  const step = duration / (nWindows + 1);
  const evenly = [];
  for (let i = 0; i < nWindows; i++) {
    evenly.push(Math.round(step * (i + 1)));
  }
  if (new Set(evenly).size === nWindows) {
    timingsSet.set(evenly.join(','), [...evenly]);
  }

  if (equalPeriods) {
    return Array.from(timingsSet.values());
  }

  const half = Math.floor(duration / 2);
  if (nWindows === 1) {
    timingsSet.set(String(half), [half]);
  } else if (nWindows >= 2) {
    const nFirst = Math.floor(nWindows / 2);
    const nSecond = nWindows - nFirst;
    const firstStep = half / (nFirst + 1);
    const secondStep = (duration - half) / (nSecond + 1);
    const firstHalf = [];
    for (let i = 0; i < nFirst; i++) firstHalf.push(Math.round(firstStep * (i + 1)));
    const secondHalf = [];
    for (let i = 0; i < nSecond; i++) secondHalf.push(Math.round(half + secondStep * (i + 1)));
    const withHalf = [...firstHalf, ...secondHalf].sort((a, b) => a - b);
    if (new Set(withHalf).size === nWindows) {
      timingsSet.set(withHalf.join(','), withHalf);
    }
  }

  for (const offset of [-5, -3, 3, 5]) {
    const candidate = evenly.map(t => Math.max(1, Math.min(duration - 1, t + offset)));
    if (new Set(candidate).size === nWindows) {
      timingsSet.set(candidate.join(','), candidate);
    }
  }

  return Array.from(timingsSet.values());
}

// --- Minutes computation ---
function computeMinutes(startingXi, subEvents, duration, allPlayerNames, slotTypeMap) {
  const stints = {};
  const timeline = {};
  const stintStart = {};
  const playerSlot = {};
  const benchStart = {};
  const onField = new Set();

  for (const name of allPlayerNames) {
    stints[name] = [];
    timeline[name] = [];
  }

  for (const [slot, player] of Object.entries(startingXi)) {
    stintStart[player] = 0;
    playerSlot[player] = slot;
    onField.add(player);
  }

  for (const name of allPlayerNames) {
    if (stintStart[name] === undefined) {
      stintStart[name] = null;
      playerSlot[name] = null;
    }
    benchStart[name] = onField.has(name) ? null : 0;
  }

  for (const ev of subEvents) {
    const t = ev.time;
    for (const swap of ev.swaps) {
      const { on: onP, off: offP, slot } = swap;
      if (stintStart[offP] !== null && stintStart[offP] !== undefined) {
        const elapsed = t - stintStart[offP];
        if (elapsed > 0) {
          stints[offP].push(elapsed);
          const pos = slotTypeMap[playerSlot[offP]] || '?';
          timeline[offP].push({ type: 'pitch', minutes: elapsed, position: pos });
        }
        stintStart[offP] = null;
      }
      benchStart[offP] = t;
      playerSlot[offP] = null;

      if (benchStart[onP] !== null && benchStart[onP] !== undefined) {
        const benchElapsed = t - benchStart[onP];
        if (benchElapsed > 0) {
          timeline[onP].push({ type: 'bench', minutes: benchElapsed });
        }
        benchStart[onP] = null;
      }
      stintStart[onP] = t;
      playerSlot[onP] = slot;

      onField.delete(offP);
      onField.add(onP);
    }
  }

  for (const p of onField) {
    if (stintStart[p] !== null && stintStart[p] !== undefined) {
      const remaining = duration - stintStart[p];
      if (remaining > 0) {
        stints[p].push(remaining);
        const pos = slotTypeMap[playerSlot[p]] || '?';
        timeline[p].push({ type: 'pitch', minutes: remaining, position: pos });
      }
    }
  }
  for (const p of allPlayerNames) {
    if (benchStart[p] !== null && benchStart[p] !== undefined) {
      const remaining = duration - benchStart[p];
      if (remaining > 0) {
        timeline[p].push({ type: 'bench', minutes: remaining });
      }
    }
  }

  return { stints, timeline };
}

// --- Constraint helpers ---
function wouldViolateBenchTogether(goingOff, goingOn, onBench, neverBenchTogether) {
  const newBench = new Set(onBench);
  newBench.add(goingOff);
  if (goingOn) newBench.delete(goingOn);
  for (const pair of neverBenchTogether) {
    if (isSubset(pair, newBench)) return true;
  }
  return false;
}

// --- Sub generation ---
function _pickSubOn(slotType, onBench, cumulative, playersByName, remaining, neverBenchTogether, goingOff, alreadyOn, tree) {
  for (const bp of onBench) {
    if (alreadyOn.includes(bp)) continue;
    const bpdata = playersByName[bp];
    if (!tree.playerCanFillSlot(bpdata.positions, slotType)) continue;
    if (cumulative[bp] + remaining > bpdata.maxMinutes) continue;
    if (wouldViolateBenchTogether(goingOff, bp, onBench, neverBenchTogether)) continue;
    return bp;
  }
  return null;
}

function _pickFairnessSwap(onField, onBench, cumulative, playersByName, slotTypeMap, playerToSlot, remaining, neverBenchTogether, tree, alreadyOn, alreadyOff) {
  const benchSorted = [...onBench].filter(bp => !alreadyOn.includes(bp)).sort((a, b) => cumulative[a] - cumulative[b]);

  for (const bp of benchSorted) {
    const bpdata = playersByName[bp];
    if (remaining <= 0) break;
    if (cumulative[bp] + remaining > bpdata.maxMinutes) continue;

    const fieldSorted = [...onField].filter(fp => !alreadyOff.includes(fp) && !alreadyOn.includes(fp)).sort((a, b) => cumulative[b] - cumulative[a]);

    for (const fp of fieldSorted) {
      if (cumulative[bp] >= cumulative[fp]) break;
      const fpdata = playersByName[fp];
      if (remaining < fpdata.minMinutes - cumulative[fp]) continue;
      const slot = playerToSlot[fp];
      const stype = slotTypeMap[slot];
      if (!tree.playerCanFillSlot(bpdata.positions, stype)) continue;
      if (wouldViolateBenchTogether(fp, bp, onBench, neverBenchTogether)) continue;
      return { on: bp, off: fp, slot };
    }
  }
  return null;
}

function _doSwap(onP, offP, slot, onField, onBench, playerToSlot, slotToPlayer, swaps) {
  const idx = onBench.indexOf(onP);
  if (idx !== -1) onBench.splice(idx, 1);
  onBench.push(offP);
  onField.delete(offP);
  onField.add(onP);
  playerToSlot[onP] = slot;
  playerToSlot[offP] = null;
  slotToPlayer[slot] = onP;
  swaps.push({ on: onP, off: offP, slot });
}

function generateSubsForWindows(timings, startingXi, benchPlayers, slots, playersByName, duration, neverBenchTogether, tree) {
  const slotToPlayer = { ...startingXi };
  const playerToSlot = {};
  for (const [slot, player] of Object.entries(startingXi)) {
    playerToSlot[player] = slot;
  }
  const onField = new Set(Object.values(startingXi));
  const onBench = [...benchPlayers];
  const slotTypeMap = {};
  for (const s of slots) slotTypeMap[s.name] = s.type;

  for (const p of onBench) playerToSlot[p] = null;

  const cumulative = {};
  for (const name of Object.keys(playersByName)) cumulative[name] = 0;

  const subEvents = [];
  let prevTime = 0;

  for (const t of timings) {
    const elapsed = t - prevTime;
    for (const p of onField) cumulative[p] += elapsed;

    const swaps = [];
    const remaining = duration - t;
    const maxSwaps = onBench.length;

    // Phase 1: Forced off
    for (const offP of [...onField]) {
      if (swaps.length >= maxSwaps) break;
      const pdata = playersByName[offP];
      if (pdata.maxMinutes >= duration || cumulative[offP] < pdata.maxMinutes) continue;
      const slot = playerToSlot[offP];
      const candidate = _pickSubOn(slotTypeMap[slot], onBench, cumulative, playersByName, remaining, neverBenchTogether, offP, swaps.map(s => s.on), tree);
      if (!candidate) return null;
      _doSwap(candidate, offP, slot, onField, onBench, playerToSlot, slotToPlayer, swaps);
    }

    // Phase 2: Opportunistic
    for (const bp of [...onBench]) {
      if (swaps.length >= maxSwaps) break;
      const bpdata = playersByName[bp];
      const stillNeeded = bpdata.minMinutes - cumulative[bp];
      if (stillNeeded <= 0 || stillNeeded > remaining) continue;
      const alreadyOn = swaps.map(s => s.on);
      const fieldSorted = [...onField].sort((a, b) => cumulative[b] - cumulative[a]);
      for (const offP of fieldSorted) {
        if (swaps.some(s => s.off === offP) || alreadyOn.includes(offP)) continue;
        const opdata = playersByName[offP];
        if (remaining < opdata.minMinutes - cumulative[offP]) continue;
        const slot = playerToSlot[offP];
        const stype = slotTypeMap[slot];
        if (!tree.playerCanFillSlot(bpdata.positions, stype)) continue;
        if (cumulative[bp] + remaining > bpdata.maxMinutes) continue;
        if (wouldViolateBenchTogether(offP, bp, onBench, neverBenchTogether)) continue;
        _doSwap(bp, offP, slot, onField, onBench, playerToSlot, slotToPlayer, swaps);
        break;
      }
    }

    // Phase 3: Fairness rotation
    while (swaps.length < maxSwaps) {
      const swap = _pickFairnessSwap(onField, onBench, cumulative, playersByName, slotTypeMap, playerToSlot, remaining, neverBenchTogether, tree, swaps.map(s => s.on), swaps.map(s => s.off));
      if (!swap) break;
      _doSwap(swap.on, swap.off, swap.slot, onField, onBench, playerToSlot, slotToPlayer, swaps);
    }

    if (swaps.length > 0) {
      subEvents.push({ time: t, swaps });
    }
    prevTime = t;
  }

  for (const p of onField) cumulative[p] += duration - prevTime;

  for (const [pname, pdata] of Object.entries(playersByName)) {
    const total = cumulative[pname];
    if (total < pdata.minMinutes || total > pdata.maxMinutes) return null;
  }

  return subEvents;
}

// --- Scoring ---
function scorePlan(stints) {
  const totals = Object.values(stints).map(s => s.reduce((a, b) => a + b, 0));
  if (totals.length === 0) return 0;
  const mean = totals.reduce((a, b) => a + b, 0) / totals.length;
  const variance = totals.reduce((a, t) => a + (t - mean) ** 2, 0) / totals.length;
  return -variance;
}

// --- Main plan generator ---
export function generatePlans(gameConfig, players, numPlans = 5) {
  const { duration, positions, subWindows, constraints } = gameConfig;
  const winMin = subWindows.min;
  const winMax = subWindows.max;
  const equalPeriods = subWindows.equalPeriods || false;

  const nbt = (constraints && constraints.neverBenchTogether || []).map(pair => new Set(pair));

  const tree = new PositionTree(positions);
  const slots = tree.getSlots();
  const playersByName = {};
  for (const p of players) playersByName[p.name] = p;

  const nSlots = slots.length;
  if (players.length < nSlots) {
    throw new Error(`You have ${players.length} players but need at least ${nSlots}.`);
  }

  const mustStartNames = new Set(players.filter(p => p.mustStart).map(p => p.name));
  const mustBenchNames = new Set(players.filter(p => p.mustBench).map(p => p.name));

  const xiOptions = findDiverseStartingXis(slots, players, mustStartNames, mustBenchNames, nbt, tree, 40);
  if (xiOptions.length === 0) {
    throw new Error('No valid starting lineup found. Check positions and constraints.');
  }

  const plans = [];
  const seenSigs = new Set();

  for (const startingXi of xiOptions) {
    const xiValues = new Set(Object.values(startingXi));
    const benchNames = players.filter(p => !xiValues.has(p.name)).map(p => p.name);

    for (let nWindows = winMin; nWindows <= winMax; nWindows++) {
      if (players.length === nSlots) continue;

      for (const timings of generateWindowTimings(duration, nWindows, equalPeriods)) {
        const subEvents = generateSubsForWindows(timings, startingXi, benchNames, slots, playersByName, duration, nbt, tree);
        if (!subEvents) continue;
        if (subEvents.length < winMin) continue;

        const slotTypeMap = {};
        for (const s of slots) slotTypeMap[s.name] = s.type;
        const { stints, timeline } = computeMinutes(startingXi, subEvents, duration, players.map(p => p.name), slotTypeMap);

        const sigParts = [
          Object.entries(startingXi).sort().map(e => e.join(':')).join(','),
          subEvents.map(e => e.time + '=' + e.swaps.map(s => [s.on, s.off, s.slot].join('>')).sort().join('+')).join(';')
        ];
        const sig = sigParts.join('||');
        if (seenSigs.has(sig)) continue;
        seenSigs.add(sig);

        const minutes = {};
        for (const name of Object.keys(stints)) {
          minutes[name] = {
            total: stints[name].reduce((a, b) => a + b, 0),
            stints: stints[name],
            timeline: timeline[name]
          };
        }

        plans.push({
          startingXi,
          bench: benchNames,
          subEvents,
          minutes,
          score: scorePlan(stints)
        });
      }
    }
  }

  plans.sort((a, b) => b.score - a.score);
  return plans.slice(0, numPlans);
}

// --- Summary grid builder ---
export function buildSummaryGrid(plan, duration) {
  const xi = plan.startingXi;
  const bench = plan.bench;
  const subs = plan.subEvents;

  const subTimes = subs.map(s => s.time);
  const boundaries = [0, ...subTimes, duration];
  const periods = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    periods.push({ start: boundaries[i], end: boundaries[i + 1] });
  }

  const allPlayers = [...Object.values(xi), ...bench];
  const playerToSlot = {};
  const onPitch = { ...xi };
  for (const [slot, player] of Object.entries(xi)) playerToSlot[player] = slot;
  for (const p of bench) playerToSlot[p] = null;

  const grid = {};
  for (const p of allPlayers) grid[p] = [];

  for (let pi = 0; pi < periods.length; pi++) {
    if (pi > 0) {
      const sub = subs[pi - 1];
      for (const swap of sub.swaps) {
        onPitch[swap.slot] = swap.on;
        playerToSlot[swap.on] = swap.slot;
        playerToSlot[swap.off] = null;
      }
    }
    for (const p of allPlayers) {
      const slot = playerToSlot[p];
      if (slot) {
        const posType = slot.replace(/\d+$/, '');
        grid[p].push(posType);
      } else {
        grid[p].push('bench');
      }
    }
  }

  return { periods, grid, allPlayers };
}
