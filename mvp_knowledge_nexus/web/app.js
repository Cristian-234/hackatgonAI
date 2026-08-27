const state = {
  payload: null,
  selectedId: null,
  filter: "all",
};

const labels = {
  project: "Proyecto",
  thesis: "Tesis",
  researcher: "Investigador",
  capability: "Capacidad",
  subject: "Asignatura",
  publication: "Publicacion",
};

const typeOrder = ["all", "project", "thesis", "researcher", "capability", "subject", "publication"];

const needSelect = document.querySelector("#needSelect");
const topRange = document.querySelector("#topRange");
const topValue = document.querySelector("#topValue");
const runButton = document.querySelector("#runButton");
const sourceTitle = document.querySelector("#sourceTitle");
const sourceMeta = document.querySelector("#sourceMeta");
const results = document.querySelector("#results");
const detail = document.querySelector("#detail");
const filters = document.querySelector("#filters");
const metrics = document.querySelector("#metrics");
const graph = document.querySelector("#graph");

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function selectedMode() {
  return document.querySelector("input[name='mode']:checked").value;
}

function priorityClass(priority) {
  return String(priority || "").toLowerCase();
}

function renderMetrics(payload) {
  const coverage = payload.metrics?.coverage_by_type || {};
  const graphNodes = payload.metrics?.graph_nodes ?? payload.graph?.summary?.nodes ?? (payload.graph?.nodes?.length ?? 0);
  const explicitEdges = payload.metrics?.explicit_edges ?? payload.graph?.summary?.explicit_edges ?? 0;
  const inferredEdges = payload.metrics?.inferred_edges ?? payload.graph?.summary?.inferred_edges ?? 0;
  metrics.innerHTML = `
    <dt>Entidades procesadas</dt><dd>${payload.metrics?.entities_processed ?? 0}</dd>
    <dt>Conexiones</dt><dd>${payload.metrics?.connections_returned ?? 0}</dd>
    <dt>Evidencias</dt><dd>${payload.metrics?.evidence_items ?? 0}</dd>
    <dt>Tipos cubiertos</dt><dd>${Object.values(coverage).filter(Boolean).length}</dd>
    <dt>Nodos grafo</dt><dd>${graphNodes}</dd>
    <dt>Aristas explícitas</dt><dd>${explicitEdges}</dd>
    <dt>Aristas inferidas</dt><dd>${inferredEdges}</dd>
  `;
}

function renderFilters(payload) {
  const counts = payload.metrics.coverage_by_type;
  filters.innerHTML = typeOrder.map((type) => {
    const label = type === "all" ? "Todo" : labels[type];
    const count = type === "all" ? payload.results.length : counts[type] || 0;
    const active = state.filter === type ? "active" : "";
    return `<button class="filter ${active}" data-filter="${type}">${label} (${count})</button>`;
  }).join("");

  filters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      renderResults();
      renderFilters(state.payload);
    });
  });
}

function filteredResults() {
  if (!state.payload) {
    return [];
  }
  if (state.filter === "all") {
    return state.payload.results;
  }
  return state.payload.results.filter((item) => item.type === state.filter);
}

function renderResults() {
  const items = filteredResults();
  if (!items.length) {
    results.innerHTML = `<p class="empty">No hay conexiones para este filtro.</p>`;
    return;
  }

  results.innerHTML = items.map((item, index) => `
    <article class="result-card ${item.id === state.selectedId ? "active" : ""}" data-id="${item.id}">
      <div class="card-head">
        <div>
          <div class="card-title">${index + 1}. ${item.id} - ${item.title}</div>
          <div class="badge-row">
            <span class="badge">${labels[item.type] || item.type}</span>
            <span class="badge ${priorityClass(item.priority)}">${item.priority}</span>
          </div>
        </div>
        <div class="score">${Math.round(item.score * 100)}%</div>
      </div>
      <p class="summary">${item.relation}</p>
    </article>
  `).join("");

  results.querySelectorAll(".result-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.selectedId = card.dataset.id;
      renderResults();
      renderDetail();
    });
  });

  if (!state.selectedId && items[0]) {
    state.selectedId = items[0].id;
    renderResults();
    renderDetail();
  }
}

function renderDetail() {
  const item = state.payload?.results.find((candidate) => candidate.id === state.selectedId);
  if (!item) {
    detail.innerHTML = `<p class="empty">Selecciona una conexion para ver evidencia, explicacion y oportunidad.</p>`;
    return;
  }

  detail.innerHTML = `
    <div>
      <div class="badge-row">
        <span class="badge">${labels[item.type] || item.type}</span>
        <span class="badge ${priorityClass(item.priority)}">${item.priority}</span>
      </div>
      <h3>${item.id} - ${item.title}</h3>
    </div>

    <section class="detail-section">
      <h4>Relacion</h4>
      <p>${item.relation}</p>
    </section>

    <section class="detail-section">
      <h4>Por que aparece</h4>
      <p>${item.why}</p>
    </section>

    <section class="detail-section">
      <h4>Oportunidad</h4>
      <p>${item.opportunity}</p>
    </section>

    <section class="detail-section">
      <h4>Evidencia trazable</h4>
      ${item.evidence.map((ev) => `
        <div class="evidence">
          <div class="source">${ev.source}</div>
          <div class="badge-row"><span class="badge">${ev.matched_terms}</span></div>
          <p class="fragment">${ev.fragment}</p>
        </div>
      `).join("")}
    </section>
  `;
}

function nodeRadius(node) {
  if (node.type === "need") {
    return 24;
  }
  if (["project", "thesis", "researcher"].includes(node.type)) {
    return 18;
  }
  return 14;
}

function truncateLabel(text, max = 24) {
  if (!text) {
    return "";
  }
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function graphPositions(nodes, edges, sourceId) {
  const width = 900;
  const height = 430;
  const source = nodes.find((node) => node.id === sourceId) || { id: sourceId, type: "need", title: sourceId };
  const directIds = new Set(
    (edges || [])
      .filter((edge) => edge.kind === "inferred")
      .flatMap((edge) => [edge.source, edge.target])
      .filter((id) => id !== sourceId)
  );
  const directNodes = (nodes || []).filter((node) => directIds.has(node.id));
  const supportNodes = (nodes || []).filter((node) => node.id !== sourceId && !directIds.has(node.id));
  const positioned = new Map();

  positioned.set(sourceId, { ...source, x: width / 2, y: height / 2 });

  directNodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(directNodes.length, 1) - Math.PI / 2;
    positioned.set(node.id, {
      ...node,
      x: width / 2 + Math.cos(angle) * 150,
      y: height / 2 + Math.sin(angle) * 130,
    });
  });

  supportNodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(supportNodes.length, 1) + Math.PI / 8;
    positioned.set(node.id, {
      ...node,
      x: width / 2 + Math.cos(angle) * 330,
      y: height / 2 + Math.sin(angle) * 178,
    });
  });

  return positioned;
}

function renderGraph() {
  const payload = state.payload;
  if (!payload?.graph?.nodes || payload.graph.nodes.length === 0) {
    graph.innerHTML = `<text x="450" y="215" text-anchor="middle" fill="#94a3b8" font-size="14">No se pudo cargar el grafo de conocimiento.</text>`;
    return;
  }

  const sourceId = payload.source?.id || "NEED-001";
  const nodes = payload.graph.nodes || [];
  const edges = payload.graph.edges || [];
  const positions = graphPositions(nodes, edges, sourceId);

  const edgeMarkup = edges.map((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) {
      return "";
    }
    const width = edge.kind === "inferred" ? Math.max(2, Math.round((edge.score || 0.2) * 5)) : 2;
    return `
      <line class="graph-edge ${edge.kind}" x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" style="stroke-width:${width}">
        <title>${edge.relation} | ${edge.evidence}</title>
      </line>
    `;
  }).join("");

  const nodeMarkup = [...positions.values()].map((node) => {
    const r = nodeRadius(node);
    const label = node.id === sourceId ? node.id : `${node.id}`;
    const dy = r + 15;
    return `
      <g class="graph-node node-${node.type}" data-id="${node.id}" transform="translate(${node.x}, ${node.y})">
        <circle r="${r}"></circle>
        <text text-anchor="middle" y="${dy}">${label}</text>
        <title>${node.id} - ${node.title}</title>
      </g>
    `;
  }).join("");

  graph.innerHTML = `${edgeMarkup}${nodeMarkup}`;
  graph.querySelectorAll(".graph-node").forEach((node) => {
    node.addEventListener("click", () => {
      const id = node.dataset.id;
      const result = payload.results.find((item) => item.id === id);
      if (result) {
        state.selectedId = id;
        state.filter = "all";
        renderFilters(payload);
        renderResults();
        renderDetail();
        return;
      }
      const graphNode = payload.graph.nodes.find((item) => item.id === id);
      const incident = payload.graph.edges.filter((edge) => edge.source === id || edge.target === id);
      detail.innerHTML = `
        <div>
          <div class="badge-row"><span class="badge">${labels[graphNode.type] || graphNode.type}</span></div>
          <h3>${graphNode.id} - ${truncateLabel(graphNode.title, 80)}</h3>
        </div>
        <section class="detail-section">
          <h4>Rol en el grafo</h4>
          <p>Este nodo aparece por relaciones explícitas conectadas a resultados inferidos.</p>
        </section>
        <section class="detail-section">
          <h4>Aristas relacionadas</h4>
          ${incident.map((edge) => `
            <div class="evidence">
              <div class="source">${edge.kind.toUpperCase()} | ${edge.source} → ${edge.target}</div>
              <p class="fragment">${edge.relation}</p>
              <div class="source">${edge.evidence}</div>
            </div>
          `).join("")}
        </section>
      `;
    });
  });
}

async function runQuery() {
  results.innerHTML = `<p class="loading">Procesando Data V1.0 y descubriendo conexiones...</p>`;
  detail.innerHTML = `<p class="empty">La evidencia aparecera al seleccionar una conexion.</p>`;

  const need = needSelect.value;
  const top = topRange.value;
  const mode = selectedMode();
  const payload = await fetchJson(`/api/connect?need=${encodeURIComponent(need)}&top=${top}&mode=${mode}`);

  state.payload = payload;
  state.selectedId = null;
  state.filter = "all";

  sourceTitle.textContent = `${payload.source.id} - ${payload.source.title}`;
  sourceMeta.textContent = `Fuente: Data V1.0 / ${payload.source.source_file}. Modo: ${payload.metrics.mode}.`;
  renderMetrics(payload);
  renderFilters(payload);
  renderResults();
  renderGraph();
}

async function init() {
  topRange.addEventListener("input", () => {
    topValue.textContent = topRange.value;
  });
  runButton.addEventListener("click", runQuery);

  const payload = await fetchJson("/api/needs");
  needSelect.innerHTML = payload.needs.map((need) => (
    `<option value="${need.id}">${need.id} - ${need.title}</option>`
  )).join("");
  needSelect.value = "NEED-001";
  await runQuery();
}

init().catch((error) => {
  results.innerHTML = `<p class="empty">No se pudo cargar el dashboard: ${error.message}</p>`;
});
