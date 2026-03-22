import { generatePlans, buildSummaryGrid, PositionTree } from './engine.js';
import * as store from './storage.js';

let currentSquad = null;
let plans = [];
let currentPlanIdx = 0;

// --- Tab navigation ---
function switchTab(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab-bar button').forEach(b => b.classList.remove('active'));
  document.getElementById('screen-' + name).classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');

  if (name === 'setup') renderSetup();
  if (name === 'players') renderPlayers();
  if (name === 'plans') renderPlansScreen();
}

function selectSquad(id) {
  store.setCurrentSquadId(id);
  currentSquad = store.getSquad(id);
  plans = [];
  currentPlanIdx = 0;
  updateTopBar();
  switchTab('setup');
}

function updateTopBar() {
  const el = document.getElementById('topSquadName');
  el.textContent = currentSquad ? `— ${currentSquad.name}` : '';
}

// --- Squads screen ---
function renderSquads() {
  const squads = store.loadSquads();
  const list = document.getElementById('squadList');
  if (squads.length === 0) {
    list.innerHTML = '<div class="empty-state"><p>No squads yet. Create one to get started.</p></div>';
    return;
  }
  list.innerHTML = squads.map(s => `
    <div class="card squad-card" onclick="app.selectSquad('${s.id}')">
      <div class="flex-between">
        <div>
          <div class="card-title">${esc(s.name)}</div>
          <div class="card-subtitle">${s.players.length} players</div>
        </div>
        <span style="font-size:20px;color:var(--text-muted)">&rsaquo;</span>
      </div>
      <div class="squad-actions" onclick="event.stopPropagation()">
        <button class="btn btn-outline btn-small" onclick="app.deleteSquadConfirm('${s.id}','${esc(s.name)}')">Delete</button>
      </div>
    </div>
  `).join('');
}

function showNewSquadForm() {
  document.getElementById('newSquadForm').style.display = 'block';
  document.getElementById('newSquadName').focus();
}
function cancelNewSquad() {
  document.getElementById('newSquadForm').style.display = 'none';
  document.getElementById('newSquadName').value = '';
}
function saveNewSquad() {
  const name = document.getElementById('newSquadName').value.trim();
  if (!name) return;
  const preset = document.getElementById('newSquadPreset').value;
  const squad = store.createSquad(name, preset);
  document.getElementById('newSquadName').value = '';
  document.getElementById('newSquadForm').style.display = 'none';
  selectSquad(squad.id);
  renderSquads();
}
function deleteSquadConfirm(id, name) {
  if (confirm(`Delete "${name}"? This cannot be undone.`)) {
    store.deleteSquad(id);
    if (currentSquad && currentSquad.id === id) {
      currentSquad = null;
      updateTopBar();
    }
    renderSquads();
  }
}

// --- Setup screen ---
function renderSetup() {
  if (!currentSquad) {
    document.getElementById('noSquadSetup').style.display = 'block';
    document.getElementById('setupContent').style.display = 'none';
    return;
  }
  document.getElementById('noSquadSetup').style.display = 'none';
  document.getElementById('setupContent').style.display = 'block';

  document.getElementById('durationVal').textContent = currentSquad.gameDefaults.duration;
  document.getElementById('subMinVal').textContent = currentSquad.gameDefaults.subWindows.min;
  document.getElementById('subMaxVal').textContent = currentSquad.gameDefaults.subWindows.max;
  document.getElementById('equalPeriods').checked = currentSquad.gameDefaults.subWindows.equalPeriods || false;

  renderPositionTree();
  renderConstraints();
  updateSlotCount();
}

function adjustDuration(delta) {
  if (!currentSquad) return;
  currentSquad.gameDefaults.duration = Math.max(10, currentSquad.gameDefaults.duration + delta);
  document.getElementById('durationVal').textContent = currentSquad.gameDefaults.duration;
  store.updateSquad(currentSquad);
}

function adjustSubWin(which, delta) {
  if (!currentSquad) return;
  const sw = currentSquad.gameDefaults.subWindows;
  sw[which] = Math.max(1, sw[which] + delta);
  if (sw.min > sw.max) sw.max = sw.min;
  document.getElementById('subMinVal').textContent = sw.min;
  document.getElementById('subMaxVal').textContent = sw.max;
  store.updateSquad(currentSquad);
}

function toggleEqualPeriods() {
  if (!currentSquad) return;
  currentSquad.gameDefaults.subWindows.equalPeriods = document.getElementById('equalPeriods').checked;
  store.updateSquad(currentSquad);
}

function renderPositionTree() {
  const container = document.getElementById('positionTree');
  container.innerHTML = buildTreeHTML(currentSquad.positions);
}

function buildTreeHTML(node, depth = 0) {
  let html = '';
  for (const [key, val] of Object.entries(node)) {
    if (typeof val === 'number') {
      html += `
        <div class="pos-tree-leaf">
          <span class="pos-tree-leaf-name">${esc(key)}</span>
          <div class="stepper">
            <button onclick="app.adjustSlot('${esc(key)}',-1)">-</button>
            <span class="stepper-val">${val}</span>
            <button onclick="app.adjustSlot('${esc(key)}',1)">+</button>
          </div>
        </div>`;
    } else {
      html += `
        <div class="pos-tree-group">
          <div class="pos-tree-group-header">${esc(key)}</div>
          <div class="pos-tree-children">${buildTreeHTML(val, depth + 1)}</div>
        </div>`;
    }
  }
  return html;
}

function adjustSlot(leafName, delta) {
  if (!currentSquad) return;
  function adjust(node) {
    for (const key of Object.keys(node)) {
      if (key === leafName && typeof node[key] === 'number') {
        node[key] = Math.max(0, node[key] + delta);
        return true;
      }
      if (typeof node[key] === 'object' && adjust(node[key])) return true;
    }
    return false;
  }
  adjust(currentSquad.positions);
  store.updateSquad(currentSquad);
  renderPositionTree();
  updateSlotCount();
}

function updateSlotCount() {
  const count = store.countSlots(currentSquad.positions);
  const avail = currentSquad.players.filter(p => p.available).length;
  document.getElementById('slotCount').textContent = `${count} slots (${avail} players available)`;
}

// --- Tree editor modal ---
function openTreeEditor() {
  document.getElementById('treeModal').classList.add('active');
  renderTreeEditor();
}
function closeTreeEditor() {
  document.getElementById('treeModal').classList.remove('active');
  renderPositionTree();
  updateSlotCount();
}

function renderTreeEditor() {
  const container = document.getElementById('treeEditorContent');
  container.innerHTML = buildEditorHTML(currentSquad.positions, []);
}

function buildEditorHTML(node, path) {
  let html = '';
  for (const [key, val] of Object.entries(node)) {
    const keyPath = [...path, key].join('.');
    if (typeof val === 'number') {
      html += `
        <div class="pos-tree-leaf" style="padding:6px 0">
          <span>${esc(key)}: ${val}</span>
          <button class="btn-icon" onclick="app.removeTreeNode('${keyPath}')" title="Remove">&times;</button>
        </div>`;
    } else {
      html += `
        <div class="pos-tree-group" style="margin-bottom:12px">
          <div class="flex-between">
            <span style="font-weight:600">${esc(key)}</span>
            <div style="display:flex;gap:4px">
              <button class="btn btn-outline btn-small" onclick="app.addTreeChild('${keyPath}')">+ add</button>
              <button class="btn-icon" onclick="app.removeTreeNode('${keyPath}')" title="Remove">&times;</button>
            </div>
          </div>
          <div class="pos-tree-children">${buildEditorHTML(val, [...path, key])}</div>
        </div>`;
    }
  }
  return html;
}

function addTopGroup() {
  const name = prompt('Group name (e.g. DEF, MID, FWD):');
  if (!name) return;
  currentSquad.positions[name.toUpperCase()] = {};
  store.updateSquad(currentSquad);
  renderTreeEditor();
}

function addTreeChild(pathStr) {
  const name = prompt('Position or group name:');
  if (!name) return;
  const isGroup = confirm('Is this a group containing other positions?\n\nOK = Group (contains sub-positions)\nCancel = Position (a slot on the pitch)');
  const node = getNodeByPath(currentSquad.positions, pathStr);
  if (node) {
    node[name.toUpperCase()] = isGroup ? {} : 1;
    store.updateSquad(currentSquad);
    renderTreeEditor();
  }
}

function removeTreeNode(pathStr) {
  const parts = pathStr.split('.');
  const key = parts.pop();
  let node = currentSquad.positions;
  for (const p of parts) node = node[p];
  delete node[key];
  store.updateSquad(currentSquad);
  renderTreeEditor();
}

function getNodeByPath(root, pathStr) {
  let node = root;
  for (const p of pathStr.split('.')) node = node[p];
  return node;
}

// --- Constraints ---
function renderConstraints() {
  const list = document.getElementById('constraintsList');
  const nbt = currentSquad.constraints.neverBenchTogether || [];
  if (nbt.length === 0) {
    list.innerHTML = '<div class="text-small text-muted">None set</div>';
  } else {
    list.innerHTML = nbt.map((pair, i) => `
      <div class="constraint-pair">
        <span class="pair-names">${esc(pair[0])} &harr; ${esc(pair[1])}</span>
        <button class="btn-icon" onclick="app.removeConstraint(${i})">&times;</button>
      </div>
    `).join('');
  }
  document.getElementById('addConstraintForm').style.display = 'none';
}

function showAddConstraint() {
  const players = currentSquad.players;
  if (players.length < 2) return;
  const optionsHtml = players.map(p => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('');
  document.getElementById('constraintA').innerHTML = optionsHtml;
  document.getElementById('constraintB').innerHTML = optionsHtml;
  document.getElementById('addConstraintForm').style.display = 'block';
}

function saveConstraint() {
  const a = document.getElementById('constraintA').value;
  const b = document.getElementById('constraintB').value;
  if (a === b) return;
  if (!currentSquad.constraints.neverBenchTogether) currentSquad.constraints.neverBenchTogether = [];
  currentSquad.constraints.neverBenchTogether.push([a, b]);
  store.updateSquad(currentSquad);
  renderConstraints();
}

function removeConstraint(idx) {
  currentSquad.constraints.neverBenchTogether.splice(idx, 1);
  store.updateSquad(currentSquad);
  renderConstraints();
}

// --- Players screen ---
function renderPlayers() {
  if (!currentSquad) {
    document.getElementById('noSquadPlayers').style.display = 'block';
    document.getElementById('playersContent').style.display = 'none';
    return;
  }
  document.getElementById('noSquadPlayers').style.display = 'none';
  document.getElementById('playersContent').style.display = 'block';

  const slotCount = store.countSlots(currentSquad.positions);
  const availCount = currentSquad.players.filter(p => p.available).length;
  const statusEl = document.getElementById('playerStatus');
  statusEl.textContent = `${availCount} available / ${slotCount} slots needed`;
  statusEl.className = 'status-bar' + (availCount < slotCount ? ' error' : availCount === slotCount ? ' warning' : '');

  const list = document.getElementById('playerList');
  list.innerHTML = currentSquad.players.map((p, i) => `
    <div class="card player-card ${p.available ? '' : 'unavailable'}" id="player-${i}">
      <div class="player-header" onclick="app.togglePlayerExpand(${i})">
        <input type="checkbox" ${p.available ? 'checked' : ''} onclick="event.stopPropagation();app.toggleAvailable(${i})">
        <span class="player-name">${esc(p.name)}</span>
        <span class="player-info">${p.positions.join(', ') || '?'} &middot; ${p.minMinutes}-${p.maxMinutes}m</span>
      </div>
      <div class="player-details">
        <div class="form-group">
          <label class="form-label">Positions</label>
          <div class="position-tags">
            ${p.positions.map((pos, pi) => `
              <span class="position-tag">${esc(pos)} <span class="remove-tag" onclick="app.removePosition(${i},${pi})">&times;</span></span>
            `).join('')}
            <button class="btn btn-outline btn-small" onclick="app.openPosPicker(${i})">+</button>
          </div>
        </div>
        <div class="flex-between mb-8">
          <span class="text-small">Min minutes</span>
          <div class="stepper">
            <button onclick="app.adjustPlayerMin(${i},-5)">-</button>
            <span class="stepper-val">${p.minMinutes}</span>
            <button onclick="app.adjustPlayerMin(${i},5)">+</button>
          </div>
        </div>
        <div class="flex-between mb-8">
          <span class="text-small">Max minutes</span>
          <div class="stepper">
            <button onclick="app.adjustPlayerMax(${i},-5)">-</button>
            <span class="stepper-val">${p.maxMinutes}</span>
            <button onclick="app.adjustPlayerMax(${i},5)">+</button>
          </div>
        </div>
        <label class="checkbox-row">
          <input type="checkbox" ${p.mustStart ? 'checked' : ''} onchange="app.toggleMustStart(${i})">
          <span class="text-small">Must start</span>
        </label>
        <label class="checkbox-row">
          <input type="checkbox" ${p.mustBench ? 'checked' : ''} onchange="app.toggleMustBench(${i})">
          <span class="text-small">Must start on bench</span>
        </label>
        <button class="btn btn-danger btn-small mt-8" onclick="app.removePlayer(${i})">Remove player</button>
      </div>
    </div>
  `).join('');
}

function toggleAvailable(idx) {
  currentSquad.players[idx].available = !currentSquad.players[idx].available;
  store.updateSquad(currentSquad);
  renderPlayers();
}

function togglePlayerExpand(idx) {
  const el = document.getElementById('player-' + idx);
  el.classList.toggle('expanded');
}

function adjustPlayerMin(idx, delta) {
  const p = currentSquad.players[idx];
  p.minMinutes = Math.max(0, Math.min(p.maxMinutes, p.minMinutes + delta));
  store.updateSquad(currentSquad);
  renderPlayers();
}

function adjustPlayerMax(idx, delta) {
  const p = currentSquad.players[idx];
  p.maxMinutes = Math.max(p.minMinutes, p.maxMinutes + delta);
  store.updateSquad(currentSquad);
  renderPlayers();
}

function toggleMustStart(idx) {
  const p = currentSquad.players[idx];
  p.mustStart = !p.mustStart;
  if (p.mustStart) p.mustBench = false;
  store.updateSquad(currentSquad);
  renderPlayers();
}

function toggleMustBench(idx) {
  const p = currentSquad.players[idx];
  p.mustBench = !p.mustBench;
  if (p.mustBench) p.mustStart = false;
  store.updateSquad(currentSquad);
  renderPlayers();
}

function removePlayer(idx) {
  const name = currentSquad.players[idx].name;
  if (!confirm(`Remove ${name}?`)) return;
  store.removePlayer(currentSquad, currentSquad.players[idx].id);
  currentSquad = store.getSquad(currentSquad.id);
  renderPlayers();
}

function showAddPlayer() {
  document.getElementById('addPlayerForm').style.display = 'block';
  document.getElementById('newPlayerName').focus();
}
function cancelNewPlayer() {
  document.getElementById('addPlayerForm').style.display = 'none';
  document.getElementById('newPlayerName').value = '';
}
function saveNewPlayer() {
  const name = document.getElementById('newPlayerName').value.trim();
  if (!name) return;
  store.addPlayer(currentSquad, name, []);
  currentSquad = store.getSquad(currentSquad.id);
  document.getElementById('newPlayerName').value = '';
  document.getElementById('addPlayerForm').style.display = 'none';
  renderPlayers();
}

function removePosition(playerIdx, posIdx) {
  currentSquad.players[playerIdx].positions.splice(posIdx, 1);
  store.updateSquad(currentSquad);
  renderPlayers();
}

// Position picker modal
let posPickerPlayerIdx = -1;
function openPosPicker(playerIdx) {
  posPickerPlayerIdx = playerIdx;
  const nodes = [{ name: 'GK', isLeaf: true, parents: [] }, ...store.getAllTreeNodes(currentSquad.positions)];
  const current = new Set(currentSquad.players[playerIdx].positions);
  const content = document.getElementById('posPickerContent');
  content.innerHTML = nodes.filter(n => !current.has(n.name)).map(n => `
    <div class="card squad-card" onclick="app.pickPosition('${esc(n.name)}')">
      <span style="font-weight:500">${esc(n.name)}</span>
      <span class="text-small text-muted" style="margin-left:8px">${n.isLeaf ? 'position' : 'group'}</span>
    </div>
  `).join('');
  document.getElementById('posPickerModal').classList.add('active');
}

function pickPosition(pos) {
  currentSquad.players[posPickerPlayerIdx].positions.push(pos);
  store.updateSquad(currentSquad);
  closePosPicker();
  renderPlayers();
}

function closePosPicker() {
  document.getElementById('posPickerModal').classList.remove('active');
}

// --- Plans screen ---
function goToPlans() {
  switchTab('plans');
}

function renderPlansScreen() {
  if (!currentSquad) {
    document.getElementById('noSquadPlans').style.display = 'block';
    document.getElementById('plansContent').style.display = 'none';
    return;
  }
  document.getElementById('noSquadPlans').style.display = 'none';
  document.getElementById('plansContent').style.display = 'block';

  if (plans.length > 0) {
    renderPlan();
  }
}

function generate() {
  if (!currentSquad) return;

  const availPlayers = currentSquad.players.filter(p => p.available);
  const slotCount = store.countSlots(currentSquad.positions);
  if (availPlayers.length < slotCount) {
    showPlanError(`Need at least ${slotCount} available players, but only ${availPlayers.length} are available.`);
    return;
  }

  document.getElementById('generateBtn').style.display = 'none';
  document.getElementById('planSpinner').classList.add('active');
  document.getElementById('planDisplay').style.display = 'none';
  document.getElementById('planError').style.display = 'none';

  // Use setTimeout to let the spinner render
  setTimeout(() => {
    try {
      const gameConfig = {
        duration: currentSquad.gameDefaults.duration,
        positions: currentSquad.positions,
        subWindows: currentSquad.gameDefaults.subWindows,
        constraints: currentSquad.constraints
      };
      const enginePlayers = availPlayers.map(p => ({
        name: p.name,
        positions: p.positions,
        minMinutes: p.minMinutes,
        maxMinutes: p.maxMinutes,
        mustStart: p.mustStart,
        mustBench: p.mustBench
      }));

      plans = generatePlans(gameConfig, enginePlayers, currentSquad.gameDefaults.numPlans || 5);
      currentPlanIdx = 0;

      document.getElementById('planSpinner').classList.remove('active');
      document.getElementById('generateBtn').style.display = 'block';

      if (plans.length === 0) {
        showPlanError('No valid plans found. Your constraints may be too tight.');
      } else {
        renderPlan();
      }
    } catch (e) {
      document.getElementById('planSpinner').classList.remove('active');
      document.getElementById('generateBtn').style.display = 'block';
      showPlanError(e.message);
    }
  }, 50);
}

function showPlanError(msg) {
  document.getElementById('planError').textContent = msg;
  document.getElementById('planError').style.display = 'block';
  document.getElementById('planDisplay').style.display = 'none';
}

function prevPlan() {
  if (currentPlanIdx > 0) { currentPlanIdx--; renderPlan(); }
}
function nextPlan() {
  if (currentPlanIdx < plans.length - 1) { currentPlanIdx++; renderPlan(); }
}

function renderPlan() {
  if (plans.length === 0) return;
  const plan = plans[currentPlanIdx];
  const duration = currentSquad.gameDefaults.duration;

  document.getElementById('planDisplay').style.display = 'block';
  document.getElementById('planError').style.display = 'none';
  document.getElementById('planLabel').textContent = `Plan ${currentPlanIdx + 1} of ${plans.length}`;

  // Get top groups from the tree
  const tree = new PositionTree(currentSquad.positions);
  const slots = tree.getSlots();
  const slotTypeMap = {};
  for (const s of slots) slotTypeMap[s.name] = s.type;

  let html = '';

  // Starting lineup
  html += '<div class="section-header">Starting Lineup</div>';
  html += renderLineup(plan.startingXi, tree);
  html += `<div class="text-small text-muted mt-8">Bench: ${plan.bench.join(', ') || '(none)'}</div>`;

  // Substitutions
  if (plan.subEvents.length > 0) {
    html += '<div class="section-header">Substitutions</div>';
    const currentXi = { ...plan.startingXi };
    for (const ev of plan.subEvents) {
      html += `<div class="sub-event">`;
      html += `<div class="sub-time">${ev.time} min</div>`;
      for (const swap of ev.swaps) {
        const pos = swap.slot.replace(/\d+$/, '');
        html += `<div class="sub-swap"><span class="on">${esc(swap.on)}</span> ON (${pos}) &larr; <span class="off">${esc(swap.off)}</span> OFF</div>`;
        currentXi[swap.slot] = swap.on;
      }
      html += '</div>';
    }
  }

  // Summary grid
  html += '<div class="section-header">Summary</div>';
  const { periods, grid, allPlayers } = buildSummaryGrid(plan, duration);
  html += '<div class="grid-wrapper"><table class="summary-grid"><thead><tr><th></th>';
  for (const p of periods) {
    html += `<th>${p.start}-${p.end}</th>`;
  }
  html += '</tr></thead><tbody>';
  for (const player of allPlayers) {
    html += `<tr><td>${esc(player)}</td>`;
    for (const cell of grid[player]) {
      const cls = getCellClass(cell, tree);
      html += `<td class="${cls}">${cell}</td>`;
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';

  // Minutes timeline
  html += '<div class="section-header">Minutes</div>';
  for (const name of Object.keys(plan.minutes).sort()) {
    const info = plan.minutes[name];
    const tl = info.timeline || [];
    const segments = tl.map(seg =>
      seg.type === 'bench' ? `bench(${seg.minutes})` : `${seg.position}(${seg.minutes})`
    ).join(' \u2192 ');
    html += `<div class="timeline-row">
      <span class="timeline-name">${esc(name)}</span>
      <span class="timeline-segments">${segments}</span>
      <span class="timeline-total">= ${info.total}m</span>
    </div>`;
  }

  document.getElementById('planBody').innerHTML = html;
}

function renderLineup(xi, tree) {
  // Group by topGroup
  const groups = {};
  const groupOrder = [];
  for (const [slotName, playerName] of Object.entries(xi)) {
    const pos = slotName.replace(/\d+$/, '');
    const topGroup = tree.topGroup[pos] || pos;
    if (!groups[topGroup]) {
      groups[topGroup] = [];
      groupOrder.push(topGroup);
    }
    groups[topGroup].push({ pos, player: playerName });
  }
  let html = '';
  for (const group of groupOrder) {
    const cls = group.toLowerCase();
    html += `<div class="lineup-group">
      <div class="lineup-players">
        ${groups[group].map(e => `<span class="lineup-chip ${getChipClass(group)}">${e.pos}: ${esc(e.player)}</span>`).join('')}
      </div>
    </div>`;
  }
  return html;
}

function getChipClass(topGroup) {
  const g = topGroup.toUpperCase();
  if (g === 'GK') return 'gk';
  if (g === 'DEF') return 'def';
  if (g === 'MID') return 'mid';
  if (g === 'FWD') return 'fwd';
  return 'bench';
}

function getCellClass(cell, tree) {
  if (cell === 'bench') return 'cell-bench';
  if (cell === 'GK') return 'cell-gk';
  const topGroup = tree.topGroup[cell];
  if (topGroup === 'DEF') return 'cell-def';
  if (topGroup === 'MID') return 'cell-mid';
  if (topGroup === 'FWD') return 'cell-fwd';
  return '';
}

// --- Helpers ---
function esc(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// --- Initialize ---
function init() {
  const savedId = store.getCurrentSquadId();
  if (savedId) {
    currentSquad = store.getSquad(savedId);
    updateTopBar();
  }
  renderSquads();
}

init();

// Register service worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}

// Export to window for onclick handlers
window.app = {
  switchTab, selectSquad, showNewSquadForm, cancelNewSquad, saveNewSquad, deleteSquadConfirm,
  adjustDuration, adjustSubWin, toggleEqualPeriods, adjustSlot,
  openTreeEditor, closeTreeEditor, addTopGroup, addTreeChild, removeTreeNode,
  showAddConstraint, saveConstraint, removeConstraint,
  toggleAvailable, togglePlayerExpand, adjustPlayerMin, adjustPlayerMax,
  toggleMustStart, toggleMustBench, removePlayer,
  showAddPlayer, cancelNewPlayer, saveNewPlayer,
  removePosition, openPosPicker, pickPosition, closePosPicker,
  goToPlans, generate, prevPlan, nextPlan,
};
