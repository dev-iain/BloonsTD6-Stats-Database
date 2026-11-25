const POP_PROPERTIES = ["lead", "black", "white", "purple", "glass", "frozen"];
const SORT_COLUMNS = [
  "range", "attack_rate", "projectile_damage", "projectile_pierce",
  "projectile_speed", "projectile_count", "ability_cooldown", "path",
];

const SEARCH_COLUMNS = [
  { key: "tower_name", label: "Tower" },
  { key: "path", label: "Path" },
  { key: "attack_rate", label: "Rate", numeric: true },
  { key: "projectile_count", label: "Count", numeric: true },
  { key: "projectile_damage", label: "Damage", numeric: true },
  { key: "projectile_pierce", label: "Pierce", numeric: true },
  { key: "projectile_speed", label: "Speed", numeric: true },
];

const RANK_COLUMNS = [
  { key: "rank", label: "#", numeric: true },
  { key: "tower_name", label: "Tower" },
  { key: "path", label: "Path" },
  { key: "total_cost", label: "Cost", numeric: true },
  { key: "dps", label: "DPS", numeric: true },
  { key: "moab_dps", label: "MOAB DPS", numeric: true },
  { key: "damage_per_dollar", label: "Damage / $", numeric: true },
];

const TOTALS_COLUMNS = [
  { key: "bloon", label: "Bloon", format: bloonLabel },
  { key: "count", label: "Count", numeric: true },
  { key: "total_rbe", label: "Total RBE", numeric: true },
];

const SPECIAL_FLAGS = [
  ["has_moab", "MOAB-class"],
  ["has_camo", "Camo"],
  ["has_lead", "Lead"],
  ["has_ceramic", "Ceramic"],
];

const ROUND_COLUMNS = [
  { key: "group_index", label: "#", numeric: true },
  { key: "bloon", label: "Bloon", format: bloonLabel },
  { key: "count", label: "Count", numeric: true },
  { key: "rbe", label: "RBE", numeric: true },
  { key: "start", label: "Start (s)", numeric: true },
  { key: "duration", label: "Duration (s)", numeric: true },
];

const RECOMMEND_COLUMNS = [
  { key: "rank", label: "#", numeric: true },
  { key: "tower_name", label: "Tower" },
  { key: "path", label: "Path" },
  { key: "upgrade_from", label: "Upgrade from" },
  { key: "total_cost", label: "Cost", numeric: true },
  { key: "score", label: "Score", numeric: true },
  { key: "first_leak_round", label: "Leaks at", numeric: true },
  { key: "reasons", label: "Reasons", format: (row) => (row.reasons || []).join(", ") },
];

function formatValue(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return String(Math.round(value * 10000) / 10000);
  return String(value);
}

function cellText(column, row) {
  return column.format ? column.format(row) : formatValue(row[column.key]);
}

function renderTable(table, columns, rows) {
  table.replaceChildren();
  if (!rows.length) return;
  const head = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = column.label;
    cell.className = column.numeric ? "num" : "";
    head.appendChild(cell);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const line = body.insertRow();
    for (const column of columns) {
      const cell = line.insertCell();
      cell.textContent = cellText(column, row);
      cell.className = column.numeric ? "num" : "";
    }
  }
}

function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

async function fetchRows(path, params) {
  const response = await fetch(`${path}?${params}`);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body.rows;
}

function formParams(form) {
  const params = new URLSearchParams();
  for (const [key, value] of new FormData(form)) {
    if (String(value).trim() !== "") params.set(key, String(value));
  }
  return params;
}

function buildPopFilters() {
  const container = document.getElementById("pop-filters");
  for (const prop of POP_PROPERTIES) {
    const label = document.createElement("label");
    label.append(`${prop} `);
    const select = document.createElement("select");
    select.name = prop;
    for (const choice of ["any", "can", "cannot"]) select.add(new Option(choice, choice));
    label.appendChild(select);
    container.appendChild(label);
  }
}

function buildSortOptions() {
  const select = document.getElementById("sort-select");
  for (const column of SORT_COLUMNS) select.add(new Option(column.replaceAll("_", " "), column));
}

async function loadDamageTypes() {
  const select = document.querySelector("#search-form [name=damage_type]");
  const response = await fetch("/api/damage-types");
  if (!response.ok) return;
  for (const name of (await response.json()).damage_types) select.add(new Option(name, name));
}

function attachSearch() {
  const form = document.getElementById("search-form");
  const status = document.getElementById("search-status");
  const table = document.getElementById("search-table");
  const run = async () => {
    try {
      const rows = await fetchRows("/api/upgrades", formParams(form));
      renderTable(table, SEARCH_COLUMNS, rows);
      setStatus(status, rows.length ? `${rows.length} upgrades` : "No upgrades match these filters.");
    } catch (error) {
      renderTable(table, SEARCH_COLUMNS, []);
      setStatus(status, error.message, true);
    }
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); run(); });
  form.addEventListener("reset", () => setTimeout(run));
  run();
}

function attachRankings() {
  const form = document.getElementById("rank-form");
  const status = document.getElementById("rank-status");
  const table = document.getElementById("rank-table");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const rows = await fetchRows("/api/rankings", formParams(form));
      const ranked = rows.map((row, index) => ({ ...row, rank: index + 1 }));
      renderTable(table, RANK_COLUMNS, ranked);
      setStatus(status, ranked.length ? "" : "No upgrades match these filters.");
    } catch (error) {
      renderTable(table, RANK_COLUMNS, []);
      setStatus(status, error.message, true);
    }
  });
  form.requestSubmit();
}

function bloonLabel(row) {
  const modifiers = [
    row.is_camo && "Camo", row.is_regrow && "Regrow", row.is_fortified && "Fortified",
  ].filter(Boolean);
  return modifiers.length ? `${modifiers.join(" ")} ${row.bloon}` : row.bloon;
}

function formatMoney(value) {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

function summaryEntries(summary) {
  return [
    { label: "Total bloons", value: summary.total_bloons.toLocaleString("en-US") },
    { label: "Total RBE", value: summary.total_rbe.toLocaleString("en-US") },
    ...SPECIAL_FLAGS.map(([key, label]) => ({
      label,
      value: summary[key] ? "Yes" : "No",
      tone: summary[key] ? "warn" : "dim",
    })),
  ];
}

function incomeEntries(income) {
  if (!income) return [{ label: "Income", value: "not loaded", tone: "dim" }];
  return [
    { label: "Pop cash", value: formatMoney(income.pop_cash), tone: "money" },
    { label: "End bonus", value: formatMoney(income.end_bonus), tone: "money" },
    { label: "Round total", value: formatMoney(income.total), tone: "money strong" },
    { label: "Cumulative", value: formatMoney(income.cumulative), tone: "money" },
  ];
}

function renderDefinitions(list, entries) {
  list.replaceChildren();
  for (const { label, value, tone } of entries) {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    if (tone) detail.className = tone;
    list.append(term, detail);
  }
}

async function fetchRound(roundNumber) {
  const response = await fetch(`/api/rounds/${encodeURIComponent(roundNumber)}`);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function renderRound(body) {
  renderDefinitions(document.getElementById("round-summary"), summaryEntries(body.summary));
  renderDefinitions(document.getElementById("round-income"), incomeEntries(body.income));
  renderTable(document.getElementById("round-totals"), TOTALS_COLUMNS, body.composition);
  renderTable(document.getElementById("round-table"), ROUND_COLUMNS, body.groups);
}

function attachRounds() {
  const form = document.getElementById("round-form");
  const status = document.getElementById("round-status");
  const detail = document.getElementById("round-detail");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      renderRound(await fetchRound(new FormData(form).get("round")));
      detail.hidden = false;
      setStatus(status, "");
    } catch (error) {
      detail.hidden = true;
      setStatus(status, error.message, true);
    }
  });
  form.requestSubmit();
}

function formatShare(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function threatEntries(threats) {
  return [
    { label: "Total RBE", value: threats.total_rbe.toLocaleString("en-US") },
    { label: "MOAB share", value: formatShare(threats.moab_share), tone: threats.moab_share ? "warn" : "dim" },
    { label: "Camo share", value: formatShare(threats.camo_share), tone: threats.camo_share ? "warn" : "dim" },
    { label: "Regrow share", value: formatShare(threats.regrow_share), tone: threats.regrow_share ? "warn" : "dim" },
    { label: "Mean layers", value: formatValue(Math.round(threats.mean_layers * 100) / 100) },
  ];
}

function propertyEntries(threats) {
  return POP_PROPERTIES.map((prop) => {
    const share = threats.property_share[prop] || 0;
    return { label: prop, value: formatShare(share), tone: share ? "warn" : "dim" };
  });
}

function renderRecommendations(threats, rows) {
  renderDefinitions(document.getElementById("recommend-threats"), threatEntries(threats));
  renderDefinitions(document.getElementById("recommend-properties"), propertyEntries(threats));
  const ranked = rows.map((row, index) => ({ ...row, rank: index + 1 }));
  renderTable(document.getElementById("recommend-table"), RECOMMEND_COLUMNS, ranked);
  return ranked.length;
}

let latestGameState = null;

function appendOwnedTowers(params) {
  const toggle = document.getElementById("recommend-live");
  if (!toggle.checked || latestGameState === null || latestGameState.stale) return 0;
  const known = latestGameState.towers.filter((tower) => tower.known);
  for (const tower of known) params.append("owned", `${tower.tower_name} ${tower.path}`);
  return known.length;
}

function ownedStatus(ownedCount, count) {
  if (ownedCount === 0) return count ? "" : "No affordable upgrade can handle this round.";
  const noun = ownedCount === 1 ? "owned tower" : "owned towers";
  const note = `Counting ${ownedCount} ${noun}.`;
  return count ? note : `${note} No affordable upgrade can handle this round.`;
}

function attachRecommend() {
  const form = document.getElementById("recommend-form");
  const status = document.getElementById("recommend-status");
  const detail = document.getElementById("recommend-detail");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const params = formParams(form);
      const ownedCount = appendOwnedTowers(params);
      const rows = await fetchRows("/api/recommendations", params);
      const round = await fetchRound(params.get("round"));
      const count = renderRecommendations(round.threats, rows);
      detail.hidden = false;
      setStatus(status, ownedStatus(ownedCount, count));
    } catch (error) {
      detail.hidden = true;
      setStatus(status, error.message, true);
    }
  });
}

const LIVE_POLL_MS = 2000;
const LIVE_FIELDS = ["round", "money", "difficulty"];

async function fetchGameState() {
  const response = await fetch("/api/game-state");
  if (response.status === 404) return null;
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function liveStatusText(state) {
  const age = Math.round(state.age_seconds);
  if (state.stale) return `Game state is stale (updated ${age}s ago). Is the game running with the mod?`;
  const towers = state.towers.length === 1 ? "1 tower" : `${state.towers.length} towers`;
  return `Live · round ${state.round} · ${formatMoney(state.money)} · ${towers} · updated ${age}s ago`;
}

function fillFromState(form, state) {
  let changed = false;
  for (const field of LIVE_FIELDS) {
    const element = form.elements[field];
    const value = String(state[field]);
    if (element.value !== value) {
      element.value = value;
      changed = true;
    }
  }
  return changed;
}

async function pollLiveState(form, liveStatus) {
  try {
    const state = await fetchGameState();
    latestGameState = state;
    if (state === null) {
      setStatus(liveStatus, "No game connected. Start the game with the mod, or run python -m btd6 fake-state.", true);
      return;
    }
    setStatus(liveStatus, liveStatusText(state), state.stale);
    if (!state.stale && fillFromState(form, state)) form.requestSubmit();
  } catch (error) {
    setStatus(liveStatus, error.message, true);
  }
}

function attachLiveToggle() {
  const form = document.getElementById("recommend-form");
  const toggle = document.getElementById("recommend-live");
  const liveStatus = document.getElementById("recommend-live-status");
  let timer = null;
  toggle.addEventListener("change", () => {
    clearInterval(timer);
    latestGameState = null;
    liveStatus.hidden = !toggle.checked;
    for (const field of ["round", "money"]) form.elements[field].readOnly = toggle.checked;
    if (!toggle.checked) return;
    pollLiveState(form, liveStatus);
    timer = setInterval(() => pollLiveState(form, liveStatus), LIVE_POLL_MS);
  });
}

async function limitRoundInput() {
  const response = await fetch("/api/rounds");
  if (!response.ok) return;
  const { first, last } = await response.json();
  if (last === null) return;
  for (const input of document.querySelectorAll("#round-form [name=round], #recommend-form [name=round]")) {
    input.min = first;
    input.max = last;
  }
}

function attachTabs() {
  const tabs = document.querySelectorAll(".tabs button");
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      for (const other of tabs) {
        const selected = other === tab;
        other.setAttribute("aria-selected", String(selected));
        document.getElementById(`tab-${other.dataset.tab}`).hidden = !selected;
      }
    });
  }
}

buildPopFilters();
buildSortOptions();
attachTabs();
attachSearch();
attachRankings();
attachRounds();
attachRecommend();
attachLiveToggle();
limitRoundInput();
loadDamageTypes();
