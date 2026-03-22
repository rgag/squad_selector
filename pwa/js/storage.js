// Storage layer for Hockey Sub Planner

const SQUADS_KEY = 'hsp_squads';
const CURRENT_KEY = 'hsp_current_squad';

// --- Formation presets ---
export const PRESETS = {
  '3-5-2': {
    DEF: { CB: 3 },
    MID: { Wing: { LM: 1, RM: 1 }, DM: 2, AM: 1 },
    FWD: { CF: 2 }
  },
  '4-4-2': {
    DEF: { FB: { LB: 1, RB: 1 }, CB: 2 },
    MID: { Wing: { LM: 1, RM: 1 }, CM: 2 },
    FWD: { CF: 2 }
  },
  '4-3-3': {
    DEF: { FB: { LB: 1, RB: 1 }, CB: 2 },
    MID: { DM: 1, CM: 2 },
    FWD: { Wing: { LW: 1, RW: 1 }, CF: 1 }
  },
  '7-a-side': {
    DEF: { LB: 1, RB: 1 },
    MID: { LM: 1, RM: 1, CM: 1 },
    FWD: { CF: 1 }
  }
};

// --- CRUD ---
export function loadSquads() {
  const raw = localStorage.getItem(SQUADS_KEY);
  return raw ? JSON.parse(raw) : [];
}

function saveSquads(squads) {
  localStorage.setItem(SQUADS_KEY, JSON.stringify(squads));
}

export function getSquad(id) {
  return loadSquads().find(s => s.id === id) || null;
}

export function createSquad(name, presetKey) {
  const squads = loadSquads();
  const positions = presetKey === 'custom' ? {} : (PRESETS[presetKey] || PRESETS['3-5-2']);
  const squad = {
    id: 'sq_' + Date.now(),
    name,
    positions: JSON.parse(JSON.stringify(positions)),
    players: [],
    gameDefaults: {
      duration: 70,
      subWindows: { min: 2, max: 6, equalPeriods: false },
      numPlans: 5
    },
    constraints: { neverBenchTogether: [] }
  };
  squads.push(squad);
  saveSquads(squads);
  return squad;
}

export function updateSquad(squad) {
  const squads = loadSquads();
  const idx = squads.findIndex(s => s.id === squad.id);
  if (idx !== -1) {
    squads[idx] = squad;
    saveSquads(squads);
  }
}

export function deleteSquad(id) {
  const squads = loadSquads().filter(s => s.id !== id);
  saveSquads(squads);
  if (getCurrentSquadId() === id) setCurrentSquadId(null);
}

export function getCurrentSquadId() {
  return localStorage.getItem(CURRENT_KEY);
}

export function setCurrentSquadId(id) {
  if (id) localStorage.setItem(CURRENT_KEY, id);
  else localStorage.removeItem(CURRENT_KEY);
}

// --- Player helpers ---
export function addPlayer(squad, name, positions) {
  squad.players.push({
    id: 'pl_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6),
    name,
    positions: positions || [],
    minMinutes: Math.floor(squad.gameDefaults.duration / 2),
    maxMinutes: squad.gameDefaults.duration,
    mustStart: false,
    mustBench: false,
    available: true
  });
  updateSquad(squad);
}

export function removePlayer(squad, playerId) {
  squad.players = squad.players.filter(p => p.id !== playerId);
  // Remove from never_bench_together
  squad.constraints.neverBenchTogether = squad.constraints.neverBenchTogether.filter(
    pair => !pair.some(name => !squad.players.find(p => p.name === name))
  );
  updateSquad(squad);
}

// --- Position tree helpers ---
export function getAllTreeNodes(positions, parentChain = []) {
  const nodes = [];
  for (const [key, val] of Object.entries(positions)) {
    if (typeof val === 'number') {
      nodes.push({ name: key, isLeaf: true, parents: [...parentChain] });
    } else {
      nodes.push({ name: key, isLeaf: false, parents: [...parentChain] });
      nodes.push(...getAllTreeNodes(val, [...parentChain, key]));
    }
  }
  return nodes;
}

export function countSlots(positions) {
  let count = 1; // GK
  for (const [key, val] of Object.entries(positions)) {
    if (typeof val === 'number') {
      count += val;
    } else {
      count += countSlots(val);
    }
  }
  return count;
}
