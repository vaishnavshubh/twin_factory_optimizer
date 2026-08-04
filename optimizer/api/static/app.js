(() => {
  const form = document.getElementById("optimize-form");
  const button = document.getElementById("run-btn");
  const statusEl = document.getElementById("status");
  const results = document.getElementById("results");
  const projectInput = document.getElementById("project-name");

  const bottleneckList = document.getElementById("bottleneck-list");
  const actionList = document.getElementById("action-list");
  const utilGrid = document.getElementById("util-grid");
  const metaProject = document.getElementById("meta-project");
  const metaMode = document.getElementById("meta-mode");
  const metaSeq = document.getElementById("meta-seq");

  function setStatus(message, tone = "") {
    statusEl.textContent = message;
    if (tone) statusEl.dataset.tone = tone;
    else delete statusEl.dataset.tone;
  }

  function severityClass(severity) {
    const value = (severity || "").toLowerCase();
    if (value === "critical" || value === "high") return `severity-${value}`;
    return "";
  }

  function renderBottlenecks(items) {
    bottleneckList.innerHTML = "";
    if (!items.length) {
      bottleneckList.innerHTML =
        "<li class='item'><p>No bottlenecks above threshold.</p></li>";
      return;
    }
    for (const item of items) {
      const li = document.createElement("li");
      li.className = `item ${severityClass(item.severity)}`;
      li.innerHTML = `
        <div class="item-title">
          <span>${escapeHtml(item.resource_name)}</span>
          <span>${Math.round(item.utilization * 100)}%</span>
        </div>
        <div class="item-meta">${escapeHtml(item.resource_id)} · ${escapeHtml(item.severity)} · threshold ${Math.round(item.threshold * 100)}%</div>
        <p>${escapeHtml(item.reason)}</p>
      `;
      bottleneckList.appendChild(li);
    }
  }

  function renderActions(items) {
    actionList.innerHTML = "";
    if (!items.length) {
      actionList.innerHTML =
        "<li class='item'><p>No actions proposed.</p></li>";
      return;
    }
    const sorted = [...items].sort((a, b) => a.priority - b.priority);
    for (const item of sorted) {
      const li = document.createElement("li");
      li.className = "item";
      li.innerHTML = `
        <div class="item-title">
          <span>${escapeHtml(item.action_type)}</span>
          <span>P${item.priority}</span>
        </div>
        <div class="item-meta">${escapeHtml(item.source_station)} → ${escapeHtml(item.target_station)} · ${escapeHtml(item.resource_id)}</div>
        <p>${escapeHtml(item.rationale)}</p>
      `;
      actionList.appendChild(li);
    }
  }

  function renderUtilization(map, threshold = 0.8) {
    utilGrid.innerHTML = "";
    const entries = Object.entries(map || {}).sort((a, b) => b[1] - a[1]);
    for (const [id, value] of entries) {
      const cell = document.createElement("div");
      const hot = value >= threshold;
      cell.className = `util-cell${hot ? " is-hot" : ""}`;
      cell.innerHTML = `
        <div class="id">${escapeHtml(id)}</div>
        <div class="val">${Math.round(value * 100)}%</div>
        <div class="util-bar"><span style="width:${Math.min(value, 1) * 100}%"></span></div>
      `;
      utilGrid.appendChild(cell);
    }
    requestAnimationFrame(() => {
      utilGrid.querySelectorAll(".util-bar > span").forEach((bar) => {
        const width = bar.style.width;
        bar.style.width = "0";
        requestAnimationFrame(() => {
          bar.style.width = width;
        });
      });
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const projectName = (projectInput.value || "tutorial").trim();

    button.disabled = true;
    button.classList.add("is-loading");
    button.textContent = "Running agents…";
    setStatus("Invoking LangGraph: reader → predictor → rerouter");

    try {
      const response = await fetch("/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: projectName }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : JSON.stringify(payload.detail || payload);
        throw new Error(detail || `Request failed (${response.status})`);
      }

      metaProject.textContent = payload.project_name;
      metaMode.textContent = payload.mode;
      metaSeq.textContent = (payload.assembly_sequence || [])
        .map((step) => step.step_id)
        .join(" → ");

      renderBottlenecks(payload.identified_bottlenecks || []);
      renderActions(payload.proposed_actions || []);
      renderUtilization(payload.current_utilization || {});

      results.classList.add("is-visible");
      results.scrollIntoView({ behavior: "smooth", block: "start" });
      setStatus(
        `Done — ${payload.identified_bottlenecks?.length || 0} bottlenecks, ${payload.proposed_actions?.length || 0} actions`,
        "ok"
      );
    } catch (error) {
      setStatus(error.message || "Optimization failed", "error");
    } finally {
      button.disabled = false;
      button.classList.remove("is-loading");
      button.textContent = "Run optimization";
    }
  });
})();
