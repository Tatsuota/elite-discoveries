/* ===========================================================================
   Elite Discoveries — front-end controller
   =========================================================================== */
const I = window.ICONS;
let DATA = null;          // full payload from /api/data
let VIEW = [];            // currently filtered + sorted systems
let REF = null;           // reference point {name, pos} for nearest-first sorting
const activeFilters = new Set();

// ?redact=1 masks ONLY the commander name (for screenshots / streaming);
// everything else stays real.
const REDACT = new URLSearchParams(location.search).has("redact");
const cmdrName = (n) => (REDACT ? "██████" : (n || "—"));

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};

// ---- formatting -----------------------------------------------------------
const fmtInt = (n) => (n == null ? "—" : Math.round(n).toLocaleString("en-US"));
function fmt(n, digits = 2, suffix = "") {
  if (n == null || isNaN(n)) return "—";
  return (+n).toLocaleString("en-US", { maximumFractionDigits: digits }) + suffix;
}
function fmtDate(iso) {
  if (!iso) return "—";
  // EDSM dates look like "2017-09-26 17:50:12" — normalise the space to "T"
  // so every browser parses it.
  const d = new Date(String(iso).replace(" ", "T"));
  if (isNaN(d)) return String(iso);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}
function fmtPeriod(days) {
  if (days == null || isNaN(days)) return "—";
  // A negative period means a RETROGRADE orbit/rotation — show the magnitude
  // plus a marker instead of a bare "-161" negative.
  const retro = days < 0;
  const d = Math.abs(days);
  if (d === 0) return "—";
  let s;
  if (d < 1) s = fmt(d * 24, 1, " h");
  else if (d > 365) s = fmt(d / 365, 1, " yr");
  else s = fmt(d, 1, " d");
  return retro ? `${s} <span class="retro" title="retrograde">↺</span>` : s;
}

// ---- boot -----------------------------------------------------------------
// The journals are read ONLY after a commander API is attached, and only for
// that commander (the journal folder can hold several ED characters).
async function boot() {
  initApi();                 // optional Inara/EDSM/Frontier profile — non-blocking
  await loadDiscoveries();   // gate: choose which commander to read
}

async function loadDiscoveries() {
  showLoading(true);
  try {
    const res = await fetch("/api/data");
    DATA = await res.json();
    if (DATA && DATA.needsCommander) { showLoading(false); await showCommanderPicker(); return; }
    revealApp();
    render();
  } catch (e) {
    revealApp();   // never leave the error in a container hidden by body.booting
    $("#systemList").innerHTML =
      `<div class="empty">Could not load your discoveries.<br>` +
      `Make sure the server is running, then press REFRESH.<br>` +
      `<span class="err">${escapeHtml(String(e && e.message || e))}</span></div>`;
  } finally {
    showLoading(false);
  }
}

// ---- commander picker (the gate — local, no API needed) -------------------
async function showCommanderPicker() {
  lockApp();
  const list = $("#commanderList");
  list.innerHTML = `<div class="muted">Reading journals&hellip;</div>`;
  let names = [];
  try { names = await (await fetch("/api/commanders")).json(); } catch (_) { /* offline */ }
  if (!names || !names.length) {
    list.innerHTML = `<div class="muted">No commanders found in your journals.</div>`;
    return;
  }
  list.innerHTML = names
    .map((n) => `<button class="cmdr-pick" data-name="${escapeHtml(n)}"><span>${escapeHtml(n)}</span></button>`)
    .join("");
}

async function selectCommander(name) {
  await fetch("/api/config", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ commander: name }),
  });
  CODEX = null;                 // different commander -> reload codex on demand
  switchView("discoveries");
  revealApp();
  await loadDiscoveries();
}

// ---- view switching + Codex -----------------------------------------------
let CODEX = null;
function switchView(view) {
  document.body.classList.toggle("view-codex", view === "codex");
  document.querySelectorAll("#viewTabs .vtab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === view));
  if (view === "codex" && !CODEX) loadCodex();
}

async function loadCodex() {
  const list = $("#codexList");
  list.innerHTML = `<div class="empty">Reading Codex&hellip;</div>`;
  try {
    CODEX = await (await fetch("/api/codex")).json();
  } catch (e) {
    list.innerHTML = `<div class="empty">Could not load Codex.<br>${e}</div>`;
    return;
  }
  if (CODEX.needsCommander) { CODEX = null; showCommanderPicker(); return; }
  renderCodex();
}

const CODEX_COLOR = {
  "Biological and Geological": "var(--cat-green)",
  "Astronomical Bodies": "var(--amber-lt)",
  "Anomalies": "var(--cat-pink)",
};

function renderCodex() {
  const c = CODEX;
  $("#codexStats").innerHTML = [
    ["codex entries", fmtInt(c.totalEntries), ""],
    ["first-logged (new)", fmtInt(c.newEntries), "gold"],
    ["categories", fmtInt(c.categories.length), "cyan"],
    ["galactic regions", fmtInt(c.regions.length), "green"],
  ].map(([l, v, cl]) => `<div class="stat"><div class="num ${cl}">${v}</div><div class="lbl">${l}</div></div>`).join("");

  const list = $("#codexList");
  if (!c.categories.length) {
    list.innerHTML = `<div class="empty">No Codex entries logged for this commander yet.</div>`;
    return;
  }
  list.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const cat of c.categories) frag.appendChild(codexCatCard(cat));
  list.appendChild(frag);
}

function codexCatCard(cat) {
  const wrap = el("div", "codex-cat");
  const subs = cat.subCategories.map((s) => `${escapeHtml(s.name)} (${s.count})`).join("  ·  ");
  const head = el("div", "codex-cat-head", `
    <div>
      <div class="cc-name" style="color:${CODEX_COLOR[cat.name] || "var(--amber-lt)"}">${escapeHtml(cat.name)}</div>
      <div class="cc-sub">${subs}</div>
    </div>
    <div class="cc-count">${fmtInt(cat.count)}<span class="chevron">&#9656;</span></div>`);

  const drawer = el("div", "codex-entries");
  head.addEventListener("click", () => {
    const open = wrap.classList.toggle("open");
    if (open && !drawer.dataset.built) {
      const frag = document.createDocumentFragment();
      for (const e of cat.entries) frag.appendChild(codexEntryCard(e));
      drawer.appendChild(frag);
      drawer.dataset.built = "1";
    }
  });
  wrap.appendChild(head);
  wrap.appendChild(drawer);
  return wrap;
}

function codexEntryCard(e) {
  const loc = [];
  if (e.region) loc.push(`Region <b>${escapeHtml(e.region)}</b>`);
  if (e.system) loc.push(`<b>${escapeHtml(e.system)}</b>${e.bodyId != null ? " &middot; body " + e.bodyId : ""}`);
  if (e.timestamp) loc.push(fmtDate(e.timestamp));
  return el("div", "codex-entry" + (e.isNew ? " new" : ""), `
    <div class="ce-name">${escapeHtml(e.name)}</div>
    <div class="ce-sub">${escapeHtml(e.subCategory || "")}</div>
    <div class="ce-loc">${loc.join("<br>")}</div>
    ${e.isNew ? `<span class="ce-new">FIRST LOGGED</span>` : ""}`);
}

function lockApp() {
  document.body.classList.remove("booting");
  document.body.classList.add("locked");
  showLoading(false);
}
function revealApp() {
  document.body.classList.remove("booting", "locked");
}

function render() {
  $("#cmdr").textContent = "CMDR " + cmdrName(DATA.commander || DATA.commanderFilter);
  $("#journalInfo").textContent = `${DATA.journalCount} journals scanned`;
  $("#genTime").textContent = "Updated " + new Date(DATA.generatedAt).toLocaleString();

  // Attached, but this commander has no discoveries in the journals.
  if (!DATA.systems || !DATA.systems.length) {
    $("#stats").innerHTML = "";
    $("#resultMeta").textContent = "";
    const found = DATA.commanders || [];
    $("#systemList").innerHTML =
      `<div class="empty">No first discoveries for the selected commander` +
      (DATA.commanderFilter ? ` &ldquo;<b>${escapeHtml(cmdrName(DATA.commanderFilter))}</b>&rdquo;` : "") + `.` +
      (found.length
        ? `<br><br>Pick a different commander with the <b>&#8644; CMDR</b> button above.`
        : "") +
      `</div>`;
    return;
  }
  buildStats();
  applyView();
}

function buildStats() {
  const t = DATA.totals;
  const cards = [
    ["systems first-discovered", fmtInt(t.systemsFirstDiscovered), ""],
    ["bodies first-discovered", fmtInt(t.bodiesFirstDiscovered), ""],
    ["bodies first-mapped", fmtInt(t.bodiesFirstMapped), "cyan"],
    ["first footfalls", fmtInt(t.firstFootfalls), "gold"],
    ["earthlikes", fmtInt(t.earthlikes), "green"],
    ["water worlds", fmtInt(t.waterWorlds), "cyan"],
    ["ammonia worlds", fmtInt(t.ammoniaWorlds), ""],
  ];
  $("#stats").innerHTML = cards
    .map(([l, v, c]) => `<div class="stat"><div class="num ${c}">${v}</div><div class="lbl">${l}</div></div>`)
    .join("");
}

// ---- filtering / sorting --------------------------------------------------
function applyView() {
  const q = $("#search").value.trim().toLowerCase();
  const sort = $("#sort").value;

  VIEW = DATA.systems.filter((s) => {
    for (const f of activeFilters) {
      if (f === "systemFirst") { if (!s.systemFirstDiscovered) return false; }
      else if (!s.flags[f]) return false;
    }
    if (q) {
      if (s.name.toLowerCase().includes(q)) return true;
      return s.bodies.some(
        (b) => (b.name || "").toLowerCase().includes(q) ||
               (b.planetClass || "").toLowerCase().includes(q) ||
               (b.starType || "").toLowerCase().includes(q));
    }
    return true;
  });

  // distance from the reference point (if one is set)
  if (REF && REF.pos) {
    for (const s of VIEW) s._dist = distanceLy(REF.pos, s.pos);
  }

  // Systems are always separated into Codex categories; the sort applies inside
  // each category group.
  const cmp = (a, b) => {
    switch (sort) {
      case "bodies": return b.scannedCount - a.scannedCount;
      case "name": return a.name.localeCompare(b.name);
      case "nearest": {
        const da = a._dist == null ? Infinity : a._dist;
        const db = b._dist == null ? Infinity : b._dist;
        return da - db;
      }
      default: return (b.discoveredAt || "").localeCompare(a.discoveredAt || "");
    }
  };
  VIEW.sort((a, b) => catRank(a) - catRank(b) || cmp(a, b));

  renderList();
}

function renderList() {
  const total = DATA.systems.length;
  const others = DATA.otherCommanders || [];
  $("#resultMeta").textContent =
    `Showing ${VIEW.length.toLocaleString()} of ${total.toLocaleString()} systems`
    + (REF ? `  ·  distances from ${REF.name}` : "")
    + (others.length
        ? `  ·  reading CMDR ${cmdrName(DATA.commander)} — ${others.length} other character${others.length > 1 ? "s" : ""} hidden`
        : "");

  const list = $("#systemList");
  list.innerHTML = "";
  if (!VIEW.length) {
    list.innerHTML = `<div class="empty">No systems match your filters.</div>`;
    return;
  }
  const frag = document.createDocumentFragment();
  let lastGroup = null;
  for (const s of VIEW) {
    const g = groupLabel(s);
    if (g !== lastGroup) {
      const count = VIEW.filter((v) => groupLabel(v) === g).length;
      frag.appendChild(el("div", `group-head gh-${s.category || "other"}`,
        `${escapeHtml(g)} <span class="gh-count">${count}</span>`));
      lastGroup = g;
    }
    const row = systemRow(s);
    row.classList.add("cat-" + (s.category || "other"));
    frag.appendChild(row);
  }
  list.appendChild(frag);
}

// ---- Codex categories (the fixed groups the systems are separated into) ----
const CATS = {
  elw:          { label: "EARTH-LIKE WORLDS",                  rank: 0 },
  water:        { label: "WATER WORLDS / WATER-BASED LIFE",    rank: 1 },
  ammonia:      { label: "AMMONIA WORLDS / AMMONIA-BASED LIFE", rank: 2 },
  waterAmmonia: { label: "WATER + AMMONIA WORLDS / BASED LIFE", rank: 3 },
  anomaly:      { label: "ANOMALIES",                          rank: 4 },
  other:        { label: "OTHER DISCOVERIES",                  rank: 5 },
};
function catRank(sys) {
  return (CATS[sys.category] || CATS.other).rank;
}
function groupLabel(sys) {
  return (CATS[sys.category] || CATS.other).label;
}

function distanceLy(a, b) {
  if (!a || !b) return null;
  const dx = a[0] - b[0], dy = a[1] - b[1], dz = a[2] - b[2];
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}
function fmtLy(d) {
  if (d == null) return "—";
  return (d < 100 ? d.toFixed(1) : Math.round(d).toLocaleString("en-US")) + " ly";
}

// ---- system row -----------------------------------------------------------
// Clean, uniform rows: every system shows just a star-class dot, its name,
// a copy button, and a chevron. Everything else lives in the dropdown.
function systemRow(sys) {
  const wrap = el("div", "system");
  wrap.dataset.addr = sys.address;

  const mainStar = sys.bodies.find((b) => b.type === "star") || {};
  const dot = `<span class="sys-dot" style="background:${mainStar.color || "#b08ad8"}"
    title="Class ${mainStar.starType || "?"} star"></span>`;

  const dist = REF ? `<span class="sys-dist">${fmtLy(sys._dist)}</span>` : "";
  const head = el("div", "sys-head" + (REF ? " with-dist" : ""), `
    ${dot}
    <span class="sys-name">${escapeHtml(sys.name)}</span>
    <span class="sys-tags">${tagsFor(sys)}</span>
    ${dist}
    <button class="copy-btn" data-copy="${escapeHtml(sys.name)}"
      title="Copy system name" aria-label="Copy system name">${I.copy}</button>
    <span class="chevron">&#9656;</span>`);

  const drawer = el("div", "bodies");
  head.addEventListener("click", (e) => {
    const copyBtn = e.target.closest(".copy-btn");
    if (copyBtn) { e.stopPropagation(); copyText(copyBtn.dataset.copy, copyBtn); return; }
    toggle(wrap, drawer, sys);
  });
  wrap.appendChild(head);
  wrap.appendChild(drawer);
  return wrap;
}

function toggle(wrap, drawer, sys) {
  const open = wrap.classList.toggle("open");
  if (open && !drawer.dataset.built) {
    drawer.appendChild(systemSummary(sys));
    const grid = el("div", "body-grid");
    const bodies = sys.bodies.slice().sort((a, b) => a.bodyId - b.bodyId);
    for (const b of bodies) grid.appendChild(bodyCard(b));
    drawer.appendChild(grid);
    drawer.dataset.built = "1";
  }
}

// The system-level info (moved out of the collapsed row), shown atop the drawer.
function systemSummary(sys) {
  // Uniform: every dropdown shows the same four stats in the same order.
  // (The feature labels live on the bar itself now.)
  const stats = [
    [`${sys.scannedCount}${sys.bodyCount ? " / " + sys.bodyCount : ""}`, "bodies scanned"],
    [fmtInt(sys.firstDiscoveredCount), "first-discovered"],
    [fmtInt(sys.firstMappedCount), "first-mapped"],
    [sys.discoveredAt ? fmtDate(sys.discoveredAt) : "—", "discovered"],
  ];

  // System context (populated bubble systems) + scan-completeness note.
  const has = (v) => v && v !== "None";   // ED reports unpopulated systems as "None"
  const ctx = [];
  if (has(sys.economy)) ctx.push(`<span class="pill">${escapeHtml(sys.economy)}</span>`);
  if (has(sys.security)) ctx.push(`<span class="pill">${escapeHtml(sys.security)} security</span>`);
  if (has(sys.allegiance)) ctx.push(`<span class="pill">${escapeHtml(sys.allegiance)}</span>`);
  if (sys.population) ctx.push(`<span class="pill">pop ${fmtInt(sys.population)}</span>`);
  if (sys.bodyCount && sys.scannedCount < sys.bodyCount) {
    ctx.push(`<span class="pill warn">${sys.bodyCount - sys.scannedCount} bodies not scanned</span>`);
  }

  return el("div", "sys-summary", `
    <div class="sys-summary-stats">
      ${stats.map(([v, l]) => `<div class="ssv"><b>${v}</b><span>${l}</span></div>`).join("")}
    </div>
    ${ctx.length ? `<div class="sys-context">${ctx.join("")}</div>` : ""}`);
}

// Text-only labels for what a system holds (shown on the collapsed bar).
function tagsFor(sys) {
  const t = [];
  if (sys.systemFirstDiscovered) t.push(`<span class="tag">FIRST DISCOVERED</span>`);
  else if (sys.firstDiscoveredCount) t.push(`<span class="tag">FIRST DISCOVERIES</span>`);
  if (sys.flags.earthlike) t.push(`<span class="tag t-elw">EARTH-LIKE</span>`);
  if (sys.flags.waterWorld) t.push(`<span class="tag t-water">WATER WORLD</span>`);
  if (sys.flags.ammonia) t.push(`<span class="tag t-ammonia">AMMONIA</span>`);
  if (sys.category === "anomaly") t.push(`<span class="tag t-anomaly">ANOMALY</span>`);
  if (sys.flags.terraformable) t.push(`<span class="tag">TERRAFORMABLE</span>`);
  if (sys.flags.bio) t.push(`<span class="tag t-ammonia">BIO</span>`);
  return t.join("");
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    ta.remove();
  }
  if (btn) {
    btn.classList.add("copied");
    btn.innerHTML = I.check;
    setTimeout(() => { btn.classList.remove("copied"); btn.innerHTML = I.copy; }, 1200);
  }
}

// ---- body card ------------------------------------------------------------
function bodyCard(body) {
  // Codex-style portraits are kept for PLANETS only — no star/belt images.
  const isPlanet = body.type === "planet";
  const card = el("div", "body-card" + (body.firstDiscovered ? " fd" : "") + (isPlanet ? "" : " np"));

  const badges = [];
  if (body.firstDiscovered) badges.push(badge("fd", "First Discovery"));
  if (body.firstMapped) badges.push(badge("fm", "First Mapped"));
  if (body.firstFootfall) badges.push(badge("ff", "First Footfall"));
  if (body.terraformable) badges.push(badge("tf", "Terraformable"));
  if (body.landable) badges.push(badge("land", "Landable"));
  const bio = body.signals && body.signals.bio;
  if (bio) badges.push(badge("bio", `${bio} Bio`));
  const geo = body.signals && body.signals.geo;
  if (geo) badges.push(badge("bio", `${geo} Geo`));

  const cls = body.type === "star"
    ? starClassLabel(body)
    : (body.planetClass || (body.type === "cluster" ? "Belt Cluster" : "—"));

  const stats = body.type === "star" ? starStats(body) : planetStats(body);

  let atmo = "";
  if (body.atmosphere && body.atmosphere !== "No atmosphere") {
    const comp = (body.atmosphereComposition || [])
      .slice(0, 4)
      .map((c) => `<span class="pill">${c.Name} ${fmt(c.Percent, 1)}%</span>`)
      .join("");
    atmo = `<div class="atmo-row">ATMOSPHERE: ${escapeHtml(body.atmosphere)}<br>${comp}</div>`;
  }
  let rings = "";
  if (body.rings && body.rings.length) {
    rings = `<div class="ring-row">${body.rings.length} RING${body.rings.length > 1 ? "S" : ""}: ` +
      body.rings.map((r) => `<span class="pill">${r.class}</span>`).join("") + `</div>`;
  }

  // Named biological genuses found here (not just the count).
  let genus = "";
  const genuses = body.signals && body.signals.genuses;
  if (genuses && genuses.length) {
    genus = `<div class="bio-row">BIO: ${genuses.map((g) => `<span class="pill">${escapeHtml(g)}</span>`).join("")}</div>`;
  }
  const comp = compositionRow(body.composition);

  if (isPlanet) {
    const portrait = el("div", "portrait");
    portrait.innerHTML = window.PORTRAITS.body(body);
    card.appendChild(portrait);
  }
  card.appendChild(el("div", "body-main", `
    <div class="body-title"><span class="bn">${escapeHtml(body.shortName || body.name)}</span>
      <span class="bc">${escapeHtml(body.name)}</span></div>
    <div class="body-class">${escapeHtml(cls)}</div>
    <div class="badges">${badges.join("")}</div>
    <div class="body-stats">${stats}</div>
    ${atmo}${genus}${comp}${rings}`));
  return card;
}

// Text-only labels — no icons/images on badges.
function badge(kind, label) {
  return `<span class="badge ${kind}">${label}</span>`;
}

function bstat(k, v) {
  return `<div class="bstat"><span class="bk">${k}</span><span class="bv">${v}</span></div>`;
}

function starClassLabel(b) {
  const sub = b.subclass != null ? b.subclass : "";
  return `Class ${b.starType || "?"}${sub}${b.luminosity ? " " + b.luminosity : ""} Star`;
}

function starStats(b) {
  return [
    bstat("Solar masses", fmt(b.stellarMass, 3)),
    bstat("Solar radii", fmt(b.solarRadii, 3)),
    bstat("Surface temp", fmt(b.surfaceTemperature, 0, " K")),
    bstat("Age", b.ageMY != null ? fmt(b.ageMY, 0) + " MY" : "—"),
    bstat("Abs. magnitude", fmt(b.absoluteMagnitude, 2)),
    b.rotationPeriodDays != null ? bstat("Rotation", fmtPeriod(b.rotationPeriodDays)) : "",
    bstat("Distance", fmt(b.distanceLS, 0, " ls")),
  ].join("");
}

function planetStats(b) {
  return [
    bstat("Gravity", fmt(b.gravityG, 2, " g")),
    bstat("Mass", fmt(b.massEM, 3, " M⊕")),
    bstat("Radius", fmt(b.earthRadii, 3, " R⊕")),
    bstat("Surface temp", fmt(b.surfaceTemperature, 0, " K")),
    bstat("Pressure", b.surfacePressure ? fmt(b.surfacePressure / 101325, 3, " atm") : "—"),
    bstat("Distance", fmt(b.distanceLS, 0, " ls")),
    bstat("Orbital period", fmtPeriod(b.orbitalPeriodDays)),
    b.rotationPeriodDays != null ? bstat("Rotation", fmtPeriod(b.rotationPeriodDays)) : "",
    b.semiMajorAxisAU != null ? bstat("Semi-major axis", fmt(b.semiMajorAxisAU, 3, " AU")) : "",
    b.eccentricity != null ? bstat("Eccentricity", fmt(b.eccentricity, 3)) : "",
    bstat("Tidal lock", b.tidalLock ? "Yes" : "No"),
    b.volcanism ? bstat("Volcanism", titleCase(b.volcanism)) : "",
    b.terraformState ? bstat("Terraform", b.terraformState) : "",
    b.probesUsed != null
      ? bstat("Mapped", `${b.probesUsed} probe${b.probesUsed === 1 ? "" : "s"}` +
          (b.efficiencyTarget && b.probesUsed <= b.efficiencyTarget ? " · efficient" : ""))
      : "",
  ].join("");
}

// Rock/Metal/Ice makeup, shown like the atmosphere-composition pills.
function compositionRow(comp) {
  if (!comp) return "";
  const parts = Object.entries(comp)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<span class="pill">${escapeHtml(k)} ${fmt(v * 100, 0)}%</span>`);
  return parts.length ? `<div class="atmo-row">COMPOSITION: ${parts.join("")}</div>` : "";
}

// ---- utils ----------------------------------------------------------------
function titleCase(s) { return s.replace(/\b\w/g, (c) => c.toUpperCase()); }
function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
// Only allow http(s) URLs into src/href; anything else (javascript:, data:, …) -> "".
function safeUrl(u) {
  if (!u) return "";
  try {
    const parsed = new URL(u, location.origin);
    return /^https?:$/.test(parsed.protocol) ? escapeHtml(parsed.href) : "";
  } catch (_) { return ""; }
}
function showLoading(on) { $("#loading").classList.toggle("show", on); }

// ---- events ---------------------------------------------------------------
let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(applyView, 160);
});
$("#sort").addEventListener("change", applyView);

// ---- FROM reference point (nearest-first) ----------------------------------
async function setReference(query) {
  const status = $("#fromStatus");
  status.textContent = "locating…";
  status.classList.remove("err");
  let res;
  try {
    res = await (await fetch(query === "__current__"
      ? "/api/locate?current=1"
      : "/api/locate?name=" + encodeURIComponent(query))).json();
  } catch (_) {
    status.textContent = "could not reach server";
    status.classList.add("err");
    return;
  }
  if (!res.ok) {
    status.textContent = res.error || "system not found";
    status.classList.add("err");
    return;
  }
  REF = { name: res.name, pos: res.pos };
  $("#fromInput").value = res.name;
  $("#fromClear").hidden = false;
  status.textContent = "";
  $("#sort").value = "nearest";
  applyView();
}

function clearReference() {
  REF = null;
  $("#fromInput").value = "";
  $("#fromClear").hidden = true;
  $("#fromStatus").textContent = "";
  if ($("#sort").value === "nearest") $("#sort").value = "recent";
  applyView();
}

$("#fromCurrent").addEventListener("click", () => setReference("__current__"));
$("#fromClear").addEventListener("click", clearReference);
$("#fromInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.value.trim()) setReference(e.target.value.trim());
});

$("#filters").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  const f = chip.dataset.filter;
  if (activeFilters.has(f)) { activeFilters.delete(f); chip.classList.remove("active"); }
  else { activeFilters.add(f); chip.classList.add("active"); }
  applyView();
});
$("#refreshBtn").addEventListener("click", async () => {
  const btn = $("#refreshBtn");
  btn.classList.add("spinning");
  btn.disabled = true;
  try {
    const res = await fetch("/api/refresh");
    DATA = await res.json();
    if (DATA && DATA.needsCommander) { await showCommanderPicker(); return; }
    CODEX = null;   // refresh re-reads journals; reload codex next time it's opened
    if (document.body.classList.contains("view-codex")) await loadCodex();
    render();
  } finally {
    btn.classList.remove("spinning");
    btn.disabled = false;
  }
});

/* ===========================================================================
   API hooks — settings modal + CMDR profile
   =========================================================================== */
async function initApi() {
  // Optional profile only (Inara/EDSM/Frontier). Never gates the discovery data —
  // that's gated by the local commander pick instead.
  $("#redirectUri").textContent = `${location.origin}/oauth/callback`;
  await loadSettings();
  await fetchCmdr();
  handleFrontierReturn();
}

async function loadSettings() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    $("#inaraCmdr").value = cfg.inara.commander || "";
    $("#edsmCmdr").value = cfg.edsm.commander || "";
    setState("#inaraState", cfg.inara.hasKey && cfg.inara.commander);
    setState("#edsmState", cfg.edsm.commander);
    setState("#frontierState", cfg.frontier.connected);
    $("#inaraKey").placeholder = cfg.inara.hasKey ? "•••••• (saved — blank keeps it)" : "API key";
    $("#edsmKey").placeholder = cfg.edsm.hasKey ? "•••••• (saved — blank keeps it)" : "API key";
    $("#frontierClient").placeholder = cfg.frontier.hasClientId ? "•••••• (saved)" : "OAuth client_id";
  } catch (_) { /* offline */ }
}

function setState(sel, on) {
  const e = $(sel);
  if (!e) return;
  e.textContent = on ? "connected" : "not connected";
  e.classList.toggle("on", !!on);
}

async function fetchCmdr() {
  let payload;
  try {
    payload = await (await fetch("/api/cmdr")).json();
  } catch (_) { return false; }
  renderCmdrCard(payload);
  return !!(payload && payload.ok);
}

function renderCmdrCard(p) {
  const card = $("#cmdrCard");
  if (!p || !p.ok || !p.profile || !p.profile.commanderName) {
    card.hidden = true;
    return;
  }
  const pr = p.profile;
  const avatarSrc = safeUrl(pr.avatarUrl);
  const avatar = avatarSrc
    ? `<img class="cmdr-avatar" src="${avatarSrc}" alt="" referrerpolicy="no-referrer">`
    : `<div class="cmdr-avatar ph">${escapeHtml((pr.commanderName || "?")[0].toUpperCase())}</div>`;

  const meta = [];
  if (pr.allegiance) meta.push(`<b>${escapeHtml(pr.allegiance)}</b>`);
  if (pr.power) meta.push(escapeHtml(pr.power));
  if (pr.squadron) meta.push(`Squadron <b>${escapeHtml(pr.squadron)}</b>`);
  if (pr.mainShip) meta.push(`Ship ${escapeHtml(pr.mainShipName || pr.mainShip)}`);
  if (pr.system) meta.push(`@ ${escapeHtml(pr.system)}`);
  if (pr.credits != null) meta.push(`${fmtInt(pr.credits)} cr`);

  const ranks = (pr.ranks || []).slice(0, 6).map((r) => {
    const v = r.title || r.name || "";
    const lbl = r.name && r.title ? r.name : (r.name || "Rank");
    return `<div class="cmdr-rank"><div class="rv">${escapeHtml(v)}</div><div class="rl">${escapeHtml(lbl)}</div></div>`;
  }).join("");

  const links = [];
  const profileHref = safeUrl(pr.profileUrl);
  if (profileHref) links.push(`<a href="${profileHref}" target="_blank" rel="noopener">View profile ↗</a>`);
  const sources = Object.entries(p.providers || {})
    .filter(([, v]) => v.ok).map(([k]) => k.toUpperCase()).join(" · ");

  card.innerHTML = `
    ${avatar}
    <div class="cmdr-id">
      <div class="nm">CMDR ${escapeHtml(cmdrName(pr.commanderName))}</div>
      <div class="meta">${meta.join(" &nbsp;•&nbsp; ") || "Profile linked"}</div>
      <div class="cmdr-links">${links.join("")}${sources ? `<span class="meta">via ${sources}</span>` : ""}</div>
    </div>
    <div class="cmdr-ranks">${ranks}</div>`;
  card.hidden = false;
}

function handleFrontierReturn() {
  const f = new URLSearchParams(location.search).get("frontier");
  if (!f) return;
  const msgs = {
    connected: ["ok", "Frontier account connected — live commander data loaded."],
    noclientid: ["err", "Add a Frontier OAuth client_id first (Settings → Frontier login)."],
    denied: ["err", "Frontier login was cancelled."],
    error: ["err", "Frontier token exchange failed — check your client_id and redirect URI."],
  };
  const m = msgs[f];
  // On success the app reveals itself; only surface the modal for errors.
  if (m && f !== "connected") { openSettings(); showSettingsStatus(m[0], m[1]); }
  history.replaceState({}, "", location.pathname);
}

function openSettings() { $("#settingsModal").hidden = false; }
function closeSettings() { $("#settingsModal").hidden = true; $("#settingsStatus").hidden = true; }
function showSettingsStatus(kind, text) {
  const s = $("#settingsStatus");
  s.className = "settings-status " + kind;
  s.textContent = text;
  s.hidden = false;
}

$("#viewTabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".vtab");
  if (tab) switchView(tab.dataset.view);
});
$("#settingsBtn").addEventListener("click", openSettings);
$("#changeCmdrBtn").addEventListener("click", showCommanderPicker);
$("#commanderList").addEventListener("click", (e) => {
  const btn = e.target.closest(".cmdr-pick");
  if (btn) selectCommander(btn.dataset.name);
});
$("#settingsModal").addEventListener("click", (e) => { if (e.target.dataset.close !== undefined) closeSettings(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSettings(); });

$("#frontierConnect").addEventListener("click", async () => {
  // persist the client_id before redirecting to Frontier
  await saveSettings(true);
  location.href = "/oauth/login";
});

$("#settingsSave").addEventListener("click", () => saveSettings(false));

async function saveSettings(silent) {
  const body = {
    inara: { apiKey: $("#inaraKey").value, commander: $("#inaraCmdr").value.trim() },
    edsm: { apiKey: $("#edsmKey").value, commander: $("#edsmCmdr").value.trim() },
    frontier: { clientId: $("#frontierClient").value },
  };
  const btn = $("#settingsSave");
  if (!silent) { btn.disabled = true; btn.textContent = "SAVING…"; }
  try {
    await fetch("/api/config", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    $("#inaraKey").value = ""; $("#edsmKey").value = ""; $("#frontierClient").value = "";
    await loadSettings();
    if (silent) return;
    showSettingsStatus("ok", "Saved. Fetching commander profile…");
    const payload = await (await fetch("/api/cmdr")).json();
    renderCmdrCard(payload);
    const errs = Object.entries(payload.providers || {}).filter(([, v]) => !v.ok);
    if (payload.ok) {
      showSettingsStatus("ok", "Profile connected ✔");
      setTimeout(closeSettings, 1100);
    } else if (errs.length) {
      showSettingsStatus("err", errs.map(([k, v]) => `${k.toUpperCase()}: ${v.error}`).join("  ·  "));
    } else {
      showSettingsStatus("err", "No providers configured yet.");
    }
  } catch (e) {
    showSettingsStatus("err", "Could not save settings: " + e);
  } finally {
    btn.disabled = false; btn.textContent = "SAVE & FETCH CMDR";
  }
}

boot();
