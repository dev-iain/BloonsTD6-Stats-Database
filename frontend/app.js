const POP_PROPERTIES = ["lead", "black", "white", "purple", "glass", "frozen"];
const SORT_COLUMNS = [
  "range", "attack_rate", "projectile_damage", "projectile_pierce",
  "projectile_speed", "projectile_count", "ability_cooldown", "path",
];
const POP_CODES = { lead: "Ld", black: "Bk", white: "Wh", purple: "Pu", glass: "Gl", frozen: "Fr" };

const SEARCH_COLUMNS = [
  { key: "tower_name", label: "Tower" },
  { key: "path", label: "Path" },
  { key: "attack_rate", label: "Rate", numeric: true },
  { key: "projectile_count", label: "Count", numeric: true },
  { key: "projectile_damage", label: "Damage", numeric: true },
  { key: "projectile_pierce", label: "Pierce", numeric: true },
  { key: "projectile_speed", label: "Speed", numeric: true },
  { key: "pops", label: "Pops", format: popsSummary },
];

const RANK_COLUMNS = [
  { key: "rank", label: "#", numeric: true },
  { key: "tower_name", label: "Tower" },
  { key: "path", label: "Path" },
  { key: "total_cost", label: "Cost", numeric: true },
  { key: "dps", label: "DPS", numeric: true },
  { key: "damage_per_dollar", label: "Damage / $", numeric: true },
];

function formatValue(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return String(Math.round(value * 10000) / 10000);
  return String(value);
}

function popsSummary(row) {
  const popped = POP_PROPERTIES.filter((prop) => row[`can_pop_${prop}`]);
  if (popped.length === POP_PROPERTIES.length) return "All";
  return popped.length ? popped.map((prop) => POP_CODES[prop]).join(" ") : "-";
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
loadDamageTypes();
