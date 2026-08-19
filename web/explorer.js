const REQUIRED_BUNDLE_FILES = [
  { name: "nodes.jsonl", inputId: "nodesFile" },
  { name: "claims.jsonl", inputId: "claimsFile" },
  { name: "evidence.jsonl", inputId: "evidenceFile" },
  { name: "unresolved.jsonl", inputId: "unresolvedFile" },
];
const MAX_INLINE_UNRESOLVED = 200;
const state = {
  nodes: [],
  claims: [],
  evidence: new Map(),
  unresolved: [],
  manifest: null,
};

const $ = (id) => document.getElementById(id);
const svgNS = "http://www.w3.org/2000/svg";

function parseJsonl(text, fileName) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try { return JSON.parse(line); }
      catch (error) {
        throw new Error(`Invalid JSON in ${fileName} on line ${index + 1}: ${error.message}`);
      }
    });
}

function decodeUtf8(buffer, fileName) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch (error) {
    throw new Error(`${fileName} is not valid UTF-8: ${error.message}`);
  }
}

function parseManifest(text) {
  let manifest;
  try {
    manifest = JSON.parse(text);
  } catch (error) {
    throw new Error(`Invalid JSON in manifest.json: ${error.message}`);
  }
  if (!manifest || Array.isArray(manifest) || typeof manifest !== "object") {
    throw new Error("manifest.json must contain a JSON object");
  }
  if (manifest.schema_version !== "1") {
    throw new Error(`Unsupported manifest schema_version: ${manifest.schema_version}`);
  }
  if (typeof manifest.snapshot_id !== "string" || !manifest.snapshot_id.trim()) {
    throw new Error("manifest.json is missing snapshot_id");
  }
  if (!manifest.files || Array.isArray(manifest.files) || typeof manifest.files !== "object") {
    throw new Error("manifest.json files must be an object");
  }
  const declaredFiles = Object.keys(manifest.files).sort();
  const requiredFiles = REQUIRED_BUNDLE_FILES.map(({ name }) => name).sort();
  if (JSON.stringify(declaredFiles) !== JSON.stringify(requiredFiles)) {
    throw new Error("manifest.json must declare exactly the four graph JSONL files");
  }
  if (!Array.isArray(manifest.sources) || !manifest.sources.length) {
    throw new Error("manifest.json must declare at least one pinned source");
  }
  if (!manifest.ontology || typeof manifest.ontology !== "object") {
    throw new Error("manifest.json is missing ontology identity");
  }
  for (const key of ["name", "version", "entities_sha256", "relations_sha256"]) {
    if (typeof manifest.ontology[key] !== "string" || !manifest.ontology[key]) {
      throw new Error(`manifest.json ontology is missing ${key}`);
    }
  }
  return manifest;
}

function selectedFile(inputId, expectedName) {
  const file = $(inputId).files[0];
  if (!file) throw new Error(`Choose ${expectedName}`);
  if (file.name !== expectedName) {
    throw new Error(`Expected ${expectedName}, selected ${file.name}`);
  }
  return file;
}

async function sha256Hex(buffer) {
  if (!globalThis.crypto?.subtle) {
    throw new Error("Web Crypto SHA-256 is unavailable in this browser");
  }
  const digest = await globalThis.crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")).join("");
}

function expectedSha256(manifest, fileName) {
  const value = manifest.files[fileName];
  if (typeof value !== "string" || !/^sha256:[a-f0-9]{64}$/i.test(value)) {
    throw new Error(`manifest.json has no valid SHA-256 for ${fileName}`);
  }
  return value.slice("sha256:".length).toLowerCase();
}

async function verifyBundleFiles(manifest, buffers) {
  const results = await Promise.all(REQUIRED_BUNDLE_FILES.map(async ({ name }) => ({
    name,
    expected: expectedSha256(manifest, name),
    actual: await sha256Hex(buffers.get(name)),
  })));
  const mismatches = results
    .filter(({ expected, actual }) => expected !== actual)
    .map(({ name }) => name);
  if (mismatches.length) {
    throw new Error(`Integrity check failed for ${mismatches.join(", ")}`);
  }
}

async function loadSelectedBundle() {
  const selected = [
    { name: "manifest.json", file: selectedFile("manifestFile", "manifest.json") },
    ...REQUIRED_BUNDLE_FILES.map(({ name, inputId }) => ({
      name,
      file: selectedFile(inputId, name),
    })),
  ];
  const buffers = new Map(await Promise.all(selected.map(async ({ name, file }) =>
    [name, await file.arrayBuffer()])));
  const manifest = parseManifest(decodeUtf8(buffers.get("manifest.json"), "manifest.json"));

  await verifyBundleFiles(manifest, buffers);

  return {
    manifest,
    nodes: parseJsonl(decodeUtf8(buffers.get("nodes.jsonl"), "nodes.jsonl"), "nodes.jsonl"),
    claims: parseJsonl(decodeUtf8(buffers.get("claims.jsonl"), "claims.jsonl"), "claims.jsonl"),
    evidence: parseJsonl(decodeUtf8(buffers.get("evidence.jsonl"), "evidence.jsonl"), "evidence.jsonl"),
    unresolved: parseJsonl(
      decodeUtf8(buffers.get("unresolved.jsonl"), "unresolved.jsonl"),
      "unresolved.jsonl",
    ),
  };
}

function nodeGroup(type = "") {
  if (/dataset|column|table|view/i.test(type)) return "Data";
  if (/contract|marker|invariant|sla/i.test(type)) return "Contract";
  return "Resource";
}

function accepted(claim) {
  const statuses = new Set(["AUTO_VERIFIED", "HUMAN_APPROVED"]);
  return statuses.has(claim.review_status) && claim.assertion_kind !== "INFERRED";
}

function element(name, attributes = {}) {
  const value = document.createElementNS(svgNS, name);
  Object.entries(attributes).forEach(([key, item]) => value.setAttribute(key, item));
  return value;
}

function showDetails(title, value) {
  const evidenceIds = value.evidence_ids || [];
  const evidence = evidenceIds.map((id) => state.evidence.get(id)).filter(Boolean);
  $("details").innerHTML = `
    <h2>${escapeHtml(title)}</h2>
    <dl>
      ${Object.entries(value)
        .filter(([key]) => !["attributes", "evidence_ids"].includes(key))
        .map(([key, item]) => `<dt>${escapeHtml(key)}</dt><dd><code>${escapeHtml(format(item))}</code></dd>`)
        .join("")}
      ${value.attributes ? `<dt>attributes</dt><dd><code>${escapeHtml(format(value.attributes))}</code></dd>` : ""}
      ${evidenceIds.length ? `<dt>evidence</dt><dd>${evidenceIds.map((id) => `<code>${escapeHtml(id)}</code>`).join("<br>")}</dd>` : ""}
      ${evidence.map((item) => `<dt>${escapeHtml(item.path)} · ${escapeHtml(item.locator)}</dt><dd><code>${escapeHtml(item.revision)}</code></dd>`).join("")}
    </dl>`;
}

function format(value) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clearGraph() {
  state.nodes = [];
  state.claims = [];
  state.evidence = new Map();
  state.unresolved = [];
  state.manifest = null;
  $("nodes").replaceChildren();
  $("edges").replaceChildren();
  $("metrics").textContent = "";
  $("empty").hidden = false;
  $("empty").textContent = "Choose manifest.json and the four JSONL files from a graph bundle.";
  $("unresolvedPanel").hidden = true;
  $("unresolvedSelect").replaceChildren();
  $("details").innerHTML = "<h2>Selection</h2><p>Select a node or edge.</p>";
}

function render() {
  const nodesLayer = $("nodes");
  const edgesLayer = $("edges");
  nodesLayer.replaceChildren();
  edgesLayer.replaceChildren();
  $("empty").hidden = state.nodes.length > 0;

  const width = Math.max($("graph").clientWidth, 780);
  const height = Math.max($("graph").clientHeight, 680);
  $("graph").setAttribute("viewBox", `0 0 ${width} ${height}`);

  const center = { x: width / 2, y: height / 2 };
  const radius = Math.max(190, Math.min(width, height) * .36);
  const positions = new Map();
  state.nodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + (index / Math.max(1, state.nodes.length)) * Math.PI * 2;
    positions.set(node.node_id, {
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
    });
  });

  const nodeIds = new Set(state.nodes.map((node) => node.node_id));
  state.claims.filter(accepted).forEach((claim) => {
    if (!nodeIds.has(claim.subject) || !nodeIds.has(claim.object)) return;
    const start = positions.get(claim.subject);
    const end = positions.get(claim.object);
    const group = element("g", { class: "edge-group", "data-search": `${claim.predicate} ${claim.subject} ${claim.object}`.toLowerCase() });
    const line = element("line", { x1: start.x, y1: start.y, x2: end.x, y2: end.y, class: "edge" });
    const hit = element("line", { x1: start.x, y1: start.y, x2: end.x, y2: end.y, class: "edge-hit" });
    const label = element("text", {
      x: (start.x + end.x) / 2,
      y: (start.y + end.y) / 2 - 5,
      class: "edge-label",
      "text-anchor": "middle",
    });
    label.textContent = claim.predicate;
    hit.addEventListener("click", () => showDetails("Claim", claim));
    group.append(line, hit, label);
    edgesLayer.append(group);
  });

  state.nodes.forEach((node) => {
    const position = positions.get(node.node_id);
    const group = element("g", {
      class: "node",
      transform: `translate(${position.x} ${position.y})`,
      "data-group": nodeGroup(node.node_type),
      "data-search": `${node.name} ${node.node_type} ${(node.aliases || []).join(" ")}`.toLowerCase(),
    });
    group.append(element("circle", { r: 25 }));
    const type = element("text", { y: -34, "text-anchor": "middle" });
    type.textContent = node.node_type;
    const name = element("text", { y: 42, "text-anchor": "middle" });
    name.textContent = node.name.length > 26 ? `${node.name.slice(0, 23)}…` : node.name;
    group.append(type, name);
    group.addEventListener("click", () => showDetails("Node", node));
    nodesLayer.append(group);
  });

  $("metrics").textContent =
    `${state.nodes.length} nodes · ${state.claims.filter(accepted).length} accepted claims · ` +
    `${state.evidence.size} evidence · ${state.unresolved.length} unresolved`;
}

function unresolvedLabel(item) {
  const context = item.target_hint || item.reason || "unresolved boundary";
  const label = `${item.unresolved_id || "unresolved"} · ${context}`;
  return label.length > 92 ? `${label.slice(0, 89)}…` : label;
}

function renderUnresolvedInspector() {
  const panel = $("unresolvedPanel");
  const summary = $("unresolvedSummary");
  const controls = $("unresolvedControls");
  const select = $("unresolvedSelect");
  panel.hidden = false;
  select.replaceChildren();

  if (!state.unresolved.length) {
    summary.textContent = "No unresolved boundaries in this verified snapshot.";
    controls.hidden = true;
    return;
  }
  if (state.unresolved.length > MAX_INLINE_UNRESOLVED) {
    summary.textContent =
      `${state.unresolved.length} unresolved boundaries. Inline inspection is limited to ` +
      `${MAX_INLINE_UNRESOLVED} records to keep this local view responsive.`;
    controls.hidden = true;
    return;
  }

  summary.textContent =
    `${state.unresolved.length} unresolved boundaries remain explicitly unproven.`;
  state.unresolved.forEach((item, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = unresolvedLabel(item);
    select.append(option);
  });
  controls.hidden = false;
}

function applyFilter() {
  const query = $("filter").value.trim().toLowerCase();
  document.querySelectorAll(".node, .edge-group").forEach((item) => {
    item.classList.toggle("dim", query && !item.dataset.search.includes(query));
  });
}

$("loadButton").addEventListener("click", async () => {
  const button = $("loadButton");
  button.disabled = true;
  clearGraph();
  $("status").dataset.state = "working";
  $("status").textContent = "Verifying bundle integrity…";
  try {
    const bundle = await loadSelectedBundle();
    state.nodes = bundle.nodes;
    state.claims = bundle.claims;
    state.evidence = new Map(bundle.evidence.map((item) => [item.evidence_id, item]));
    state.unresolved = bundle.unresolved;
    state.manifest = bundle.manifest;
    $("status").dataset.state = "verified";
    $("status").textContent = `Verified ${state.manifest.snapshot_id}`;
    render();
    renderUnresolvedInspector();
    applyFilter();
  } catch (error) {
    $("status").dataset.state = "error";
    $("status").textContent = error.message;
    $("empty").textContent = "Bundle not loaded. Fix the selected files and try again.";
  } finally {
    button.disabled = false;
  }
});

$("inspectUnresolvedButton").addEventListener("click", () => {
  const index = Number($("unresolvedSelect").value);
  const item = state.unresolved[index];
  if (item) showDetails("Unresolved boundary", item);
});

$("filter").addEventListener("input", applyFilter);
window.addEventListener("resize", () => state.nodes.length && render());
