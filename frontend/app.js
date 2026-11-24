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

async function limitRoundInput() {
  const response = await fetch("/api/rounds");
  if (!response.ok) return;
  const { first, last } = await response.json();
  const input = document.querySelector("#round-form [name=round]");
  if (last !== null) { input.min = first; input.max = last; }
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
limitRoundInput();
loadDamageTypes();
