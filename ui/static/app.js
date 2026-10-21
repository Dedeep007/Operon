"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);
  const examples = {
    company:
      "Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.",
    balaji_blueprint:
      "Find the blue print of balaji construction, inspect the architectural specifications, and verify the record.",
    balaji_onboard:
      "Read the vendor profile for Balaji Construction and register them into our internal ERP.",
    acme: "Find the latest invoice from Acme Logistics, enter it into our ERP, and verify the amount and due date.",
    globex:
      "Find the latest invoice from Globex Software, register it in accounting, and verify the ledger.",
    omni: "Find the latest invoice from OmniCorp Industries, enter it into our ERP, and verify the result.",
    apex: "Read the vendor profile for Apex Technologies and register them into our internal ERP.",
    quantum:
      "Read the vendor profile for Quantum Cloud Systems and register them into our internal ERP.",
  };
  const terminal = new Set([
    "completed",
    "failed",
    "partially_completed",
    "interrupted",
  ]);
  const labels = {
    queued: "Queued",
    running: "Working",
    waiting_approval: "Needs approval",
    completed: "Completed",
    failed: "Failed",
    partially_completed: "Partially completed",
    interrupted: "Interrupted",
  };
  const factLabels = {
    invoice_number: "Invoice",
    amount: "Amount (USD)",
    due_date: "Due date",
    vendor_name: "Vendor",
    vendor_id: "Vendor ID",
    tax_id: "Tax ID",
    payment_terms: "Payment terms",
    contact_email: "Contact",
  };
  let source = null,
    currentRun = null,
    currentApproval = null,
    busy = false,
    seen = new Set();

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  async function api(path, options) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "The request could not be completed. Check the task and try again.",
      );
    return data;
  }
  const post = (path, data) =>
    api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  function notice(message) {
    $("notice").textContent = message || "";
    $("notice").classList.toggle("hidden", !message);
  }
  function setBusy(value) {
    busy = value;
    ["btn-run", "btn-preview", "btn-reset-erp"].forEach(
      (id) => ($(id).disabled = value),
    );
    $("task-input").disabled = value;
    $("example-select").disabled = value;
  }
  function setStatus(status) {
    $("run-status").textContent = labels[status] || status;
    $("run-status").className =
      "status-label " +
      (status === "waiting_approval"
        ? "waiting"
        : status === "partially_completed" || status === "interrupted"
          ? "failed"
          : status);
  }
  function reset(run) {
    currentRun = run;
    currentApproval = null;
    seen = new Set();
    $("approval-panel").classList.add("hidden");
    $("evidence-banner").classList.add("hidden");
    $("recovery-note").classList.add("hidden");
    $("preview-note").classList.toggle("hidden", run.mode !== "preview");
    $("run-caption").textContent =
      (run.mode === "preview" ? "Preview" : "Task") +
      " · " +
      new Date(run.created_at).toLocaleString();
    $("plan-container").replaceChildren(
      element("li", "muted", "Preparing the plan…"),
    );
    $("plan-count").textContent = "0 steps";
    $("entities-list").replaceChildren(
      element("p", "muted", "Reading source details…"),
    );
    $("fact-count").textContent = "0";
    $("source-list").replaceChildren(
      element("li", "muted", "No documents read yet."),
    );
    $("verif-title").textContent = "Checking after execution";
    $("verification-symbol").textContent = "○";
    $("verif-description").textContent =
      "The result will be compared with source facts and the ledger.";
    $("verif-checklist").replaceChildren();
    $("verif-evidence").textContent = "";
    setStatus(run.status);
    setBusy(!terminal.has(run.status));
    notice(run.error || "");
  }
  async function start(mode) {
    const task = $("task-input").value.trim();
    if (!task || busy) return;
    notice("");
    setBusy(true);
    try {
      const run = await post("/api/runs", { task, mode });
      await openRun(run.id);
    } catch (error) {
      notice(error.message);
      setBusy(false);
    }
  }
  async function openRun(id) {
    if (source) source.close();
    try {
      const run = await api(`/api/runs/${id}`);
      reset(run);
      $("task-input").value = run.task;
      localStorage.setItem("operon.lastRun", id);
      source = new EventSource(`/api/runs/${id}/events`);
      source.onmessage = (message) => {
        if (!currentRun || currentRun.id !== id) return;
        const event = JSON.parse(message.data);
        if (seen.has(event.seq)) return;
        seen.add(event.seq);
        consume(event);
      };
      source.onerror = () => {
        if (source.readyState === EventSource.CONNECTING)
          notice(
            "Connection interrupted. Reconnecting to this task’s saved events…",
          );
      };
      source.onopen = () => notice("");
      await loadHistory();
    } catch (error) {
      notice(error.message);
      setBusy(false);
    }
  }
  function consume(event) {
    if (event.event === "start") setStatus("running");
    if (event.event === "node_update") {
      if (event.planner_backend)
        $("model-name").textContent =
          event.planner_backend === "groq"
            ? "Groq model planner"
            : `Offline workflow planner${event.planner_backend.includes("unavailable") ? " · Groq unavailable" : ""}`;
      if (event.plan) renderPlan(event.plan);
      if (event.scratchpad) renderMemory(event.scratchpad);
      if (event.verification) renderVerification(event.verification);
      if (event.evidence_packet) renderReport(event.evidence_packet);
      if (event.errors && event.errors.length) {
        const error = event.errors[event.errors.length - 1];
        $("recovery-note").textContent =
          error.recovery_strategy || error.message;
        $("recovery-note").classList.remove("hidden");
      }
    } else if (event.event === "approval_required") {
      currentApproval = event.approval;
      $("approval-prompt").textContent = currentApproval.prompt;
      $("approval-args").textContent = JSON.stringify(
        currentApproval.tool_args,
        null,
        2,
      );
      $("approval-panel").classList.remove("hidden");
      setStatus("waiting_approval");
      setBusy(true);
      $("btn-approve").disabled = false;
      $("btn-reject").disabled = false;
      loadHistory().catch((error) => notice(error.message));
    } else if (event.event === "approval_decision") {
      $("approval-panel").classList.add("hidden");
      setStatus("running");
    } else if (event.event === "error") notice(event.message);
    else if (event.event === "end") {
      source.close();
      setBusy(false);
      setStatus(event.status);
      $("approval-panel").classList.add("hidden");
      loadHistory().catch((error) => notice(error.message));
      loadLedger();
    }
  }
  function renderPlan(steps) {
    const expanded = new Set(
      Array.from($("plan-container").querySelectorAll("details[open]")).map(
        (d) => d.dataset.step,
      ),
    );
    $("plan-container").replaceChildren();
    $("plan-count").textContent =
      `${steps.filter((s) => s.status === "completed").length} / ${steps.length} done`;
    const states = {
      pending: "Pending",
      in_progress: "Working",
      completed: "Done",
      failed: "Failed",
      skipped: "Stopped",
    };
    steps.forEach((step) => {
      const row = element("li", `step-item ${step.status}`);
      row.append(
        element(
          "span",
          "step-marker",
          step.status === "completed" ? "✓" : String(step.step_id),
        ),
      );
      const heading = element("div", "step-heading");
      heading.append(
        element("span", "step-title", step.description),
        element("span", "step-state", states[step.status] || step.status),
      );
      const detail = element("details", "step-detail");
      detail.dataset.step = String(step.step_id);
      detail.open = expanded.has(detail.dataset.step);
      detail.append(
        element("summary", "", "View action details"),
        element(
          "pre",
          "",
          `${step.tool_name}\n${JSON.stringify(step.tool_args, null, 2)}${step.error ? "\n\n" + step.error : ""}`,
        ),
      );
      row.append(heading, detail);
      $("plan-container").append(row);
    });
  }
  function renderMemory(memory) {
    $("entities-list").replaceChildren();
    const facts = Object.entries(memory.entities || {}).filter(
      ([key]) => factLabels[key],
    );
    $("fact-count").textContent = String(facts.length);
    facts.forEach(([key, value]) => {
      $("entities-list").append(
        element("dt", "", factLabels[key]),
        element(
          "dd",
          "",
          key === "amount"
            ? Number(value).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })
            : String(value),
        ),
      );
    });
    if (memory.source_documents && memory.source_documents.length)
      renderSources(memory.source_documents);
  }
  function renderSources(sources) {
    $("source-list").replaceChildren();
    sources.forEach((doc) => {
      const row = element("li", "", doc.file_path.split(/[\\/]/).pop());
      const hash = element(
        "small",
        "",
        `SHA-256 · ${doc.sha256.slice(0, 20)}…`,
      );
      hash.title = doc.sha256;
      row.append(hash);
      $("source-list").append(row);
    });
  }
  function renderVerification(result) {
    $("verification-symbol").textContent = result.is_verified ? "✓" : "!";
    $("verif-title").textContent = result.is_verified
      ? "Outcome verified"
      : "Could not verify completion";
    $("verif-description").textContent = result.is_verified
      ? "The stored record matches the source facts."
      : result.discrepancies.join(" ");
    $("verif-checklist").replaceChildren(
      ...(result.checks_performed || []).map((text) => element("li", "", text)),
    );
    $("verif-evidence").textContent = result.evidence;
  }
  function renderReport(packet) {
    const ok = packet.status === "completed";
    $("evidence-banner").className = "report-panel" + (ok ? "" : " failed");
    $("report-title").textContent =
      packet.mode === "preview"
        ? ok
          ? "Preview verified"
          : "Preview needs attention"
        : ok
          ? "Outcome verified"
          : "Task needs attention";
    $("evidence-summary-text").textContent = packet.summary;
    $("stat-actions").textContent = packet.total_actions_taken;
    $("stat-time").textContent = `${packet.execution_time_seconds}s`;
    $("stat-diff").textContent = packet.created_records.length;
    $("policy-summary").textContent = packet.policy_checks.length
      ? `${packet.policy_checks.length} action requiring approval${packet.mode === "preview" ? " on execution" : " reviewed"}`
      : "Within approval policy";
    $("state-diff").textContent = JSON.stringify(packet.state_diffs, null, 2);
    $("evidence-digest").textContent =
      `Evidence SHA-256: ${packet.evidence_sha256}`;
    $("download-evidence").href = `/api/runs/${packet.run_id}/evidence`;
    renderSources(packet.source_documents);
  }
  async function decide(approved) {
    if (!currentApproval) return;
    $("btn-approve").disabled = true;
    $("btn-reject").disabled = true;
    try {
      await post(`/api/runs/${currentRun.id}/approval`, {
        approval_id: currentApproval.approval_id,
        approved,
      });
      $("approval-panel").classList.add("hidden");
      currentApproval = null;
    } catch (error) {
      notice(error.message);
      $("btn-approve").disabled = false;
      $("btn-reject").disabled = false;
    }
  }
  async function loadHistory() {
    const runs = await api("/api/runs");
    $("run-history").replaceChildren();
    if (!runs.length)
      $("run-history").append(
        element("p", "muted", "Your completed tasks will live here."),
      );
    runs.forEach((run) => {
      const button = element(
        "button",
        "history-item" +
          (currentRun && run.id === currentRun.id ? " selected" : ""),
      );
      button.append(element("span", "history-task", run.task));
      const meta = element("span", "history-meta");
      meta.append(
        element(
          "span",
          "",
          (run.mode === "preview" ? "Preview · " : "") +
            (labels[run.status] || run.status),
        ),
        element(
          "time",
          "",
          new Date(run.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        ),
      );
      button.append(meta);
      button.addEventListener("click", () => openRun(run.id));
      $("run-history").append(button);
    });
    return runs;
  }
  async function loadLedger() {
    try {
      const data = await api("/api/erp/state");
      $("erp-table-body").replaceChildren();
      Object.values(data.invoices).forEach((invoice) => {
        const row = element(
          "tr",
          invoice.source === "autonomous_worker" ? "new-record" : "",
        );
        row.append(
          element("td", "", invoice.invoice_number),
          element("td", "", invoice.vendor_name),
          element(
            "td",
            "amount",
            Number(invoice.amount).toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            }),
          ),
          element("td", "", invoice.due_date),
        );
        const status = element("td");
        status.append(
          element(
            "span",
            "ledger-status " + invoice.status.toLowerCase(),
            invoice.status,
          ),
        );
        row.append(status);
        $("erp-table-body").append(row);
      });
      $("vendor-count").textContent =
        `Vendor directory · ${data.vendor_count} registered`;
      $("vendor-list").replaceChildren();
      Object.values(data.vendors).forEach((v) => {
        const row = element("div", "vendor-card");
        row.append(
          element("strong", "", v.name),
          element(
            "span",
            "",
            `${v.vendor_id} · ${v.tax_id} · ${v.payment_terms}`,
          ),
        );
        $("vendor-list").append(row);
      });
    } catch (error) {
      notice(error.message);
    }
  }

  $("today").textContent = new Date().toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  $("btn-run").addEventListener("click", () => start("execute"));
  $("btn-preview").addEventListener("click", () => start("preview"));
  $("btn-approve").addEventListener("click", () => decide(true));
  $("btn-reject").addEventListener("click", () => decide(false));
  $("example-select").addEventListener("change", (event) => {
    if (examples[event.target.value])
      $("task-input").value = examples[event.target.value];
  });
  $("btn-refresh-erp").addEventListener("click", loadLedger);
  $("btn-refresh-history").addEventListener("click", () =>
    loadHistory().catch((error) => notice(error.message)),
  );
  $("history-toggle").addEventListener("click", () => {
    const opened = document
      .querySelector(".sidebar")
      .classList.toggle("history-open");
    $("history-toggle").setAttribute("aria-expanded", String(opened));
  });
  $("btn-reset-erp").addEventListener("click", async () => {
    try {
      await post("/api/erp/reset", {});
      notice("");
      await loadLedger();
    } catch (error) {
      notice(error.message);
    }
  });
  api("/api/info")
    .then((info) => ($("model-name").textContent = info.model_name))
    .catch((error) => notice(error.message));
  loadLedger();
  loadHistory()
    .then((runs) => {
      const active = runs.find((run) => !terminal.has(run.status));
      const saved = localStorage.getItem("operon.lastRun");
      if (active) return openRun(active.id);
      if (saved && runs.some((run) => run.id === saved)) return openRun(saved);
    })
    .catch((error) => notice(error.message));
});
