// Operon Dashboard Real-Time Client

document.addEventListener("DOMContentLoaded", () => {
    const taskInput = document.getElementById("task-input");
    const btnRun = document.getElementById("btn-run");
    const chips = document.querySelectorAll(".chip");
    const planContainer = document.getElementById("plan-container");
    const entitiesList = document.getElementById("entities-list");
    const stepResultsList = document.getElementById("step-results-list");
    const erpTableBody = document.getElementById("erp-table-body");
    const loopStatus = document.getElementById("loop-status");
    const verifScore = document.getElementById("verif-score");
    const verifMeter = document.querySelector(".verif-meter");
    const verifStatusTitle = document.getElementById("verif-status-title");
    const verifStatusDesc = document.getElementById("verif-status-desc");
    const verifChecklist = document.getElementById("verif-checklist");
    const verifEvidence = document.getElementById("verif-evidence");
    const verifBadge = document.getElementById("verif-badge");
    const evidenceBanner = document.getElementById("evidence-banner");
    const evidenceSummary = document.getElementById("evidence-summary-text");
    const statActions = document.getElementById("stat-actions");
    const statTime = document.getElementById("stat-time");
    const statDiff = document.getElementById("stat-diff");
    const btnResetErp = document.getElementById("btn-reset-erp");
    const btnRefreshErp = document.getElementById("btn-refresh-erp");
    const modelNameEl = document.getElementById("model-name");

    let eventSource = null;

    // Load initial system and ERP state
    loadSystemInfo();
    loadErpState();

    // Preset chips
    chips.forEach(chip => {
        chip.addEventListener("click", () => {
            chips.forEach(c => c.classList.remove("active"));
            chip.classList.add("active");
            taskInput.value = chip.getAttribute("data-task");
        });
    });

    btnResetErp.addEventListener("click", async () => {
        await fetch("/api/erp/reset", { method: "POST" });
        loadErpState();
    });

    btnRefreshErp.addEventListener("click", loadErpState);

    // Run Task
    btnRun.addEventListener("click", () => {
        const task = taskInput.value.trim();
        if (!task) return;
        runAutonomousTask(task);
    });

    async function loadSystemInfo() {
        try {
            const res = await fetch("/api/info");
            const data = await res.json();
            if (data.model_name) {
                modelNameEl.textContent = `${data.model_name} (${data.is_live_groq ? 'Live Groq LPU' : 'Simulation'})`;
            }
        } catch (e) {
            console.error(e);
        }
    }

    async function loadErpState() {
        try {
            const res = await fetch("/api/erp/state");
            const data = await res.json();
            renderErpTable(data.invoices || {});
        } catch (e) {
            console.error(e);
        }
    }

    function renderErpTable(invoices) {
        erpTableBody.innerHTML = "";
        const list = Object.values(invoices);
        if (list.length === 0) {
            erpTableBody.innerHTML = `<tr><td colspan="5" class="center-text">No records in ledger.</td></tr>`;
            return;
        }

        list.forEach(inv => {
            const tr = document.createElement("tr");
            const isNew = inv.source === "autonomous_worker";
            tr.innerHTML = `
                <td><strong>${inv.invoice_number}</strong> ${isNew ? '<span class="badge-tag">NEW</span>' : ''}</td>
                <td>${inv.vendor_name || inv.vendor_id}</td>
                <td>$${Number(inv.amount).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                <td>${inv.due_date}</td>
                <td><span class="${inv.status === 'PAID' ? 'badge-paid' : 'badge-pending'}">${inv.status}</span></td>
            `;
            erpTableBody.appendChild(tr);
        });
    }

    function setNodeActive(nodeName) {
        document.querySelectorAll(".pipeline-node").forEach(n => {
            n.classList.remove("active");
        });
        const target = document.getElementById(`node-${nodeName}`);
        if (target) {
            target.classList.add("active");
            target.classList.add("completed");
        }
    }

    function resetVisualizer() {
        document.querySelectorAll(".pipeline-node").forEach(n => {
            n.classList.remove("active", "completed");
        });
        evidenceBanner.classList.add("hidden");
        verifChecklist.innerHTML = "";
        verifEvidence.textContent = "";
        verifScore.textContent = "0%";
        verifMeter.classList.remove("verified");
        verifBadge.textContent = "RUNNING";
        verifBadge.className = "badge-status running";
        loopStatus.textContent = "RUNNING";
        loopStatus.className = "badge-status running";
    }

    function runAutonomousTask(task) {
        if (eventSource) {
            eventSource.close();
        }

        resetVisualizer();
        btnRun.disabled = true;
        btnRun.querySelector(".btn-text").textContent = "Executing...";

        eventSource = new EventSource(`/api/stream?task=${encodeURIComponent(task)}`);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.event === "start") {
                setNodeActive("planner");
            } else if (data.event === "node_update") {
                setNodeActive(data.node);

                if (data.plan) {
                    renderPlan(data.plan);
                }

                if (data.scratchpad) {
                    renderMemory(data.scratchpad);
                }

                if (data.verification) {
                    renderVerification(data.verification);
                    loadErpState();
                }

                if (data.evidence_packet) {
                    renderEvidencePacket(data.evidence_packet);
                    loadErpState();
                }
            } else if (data.event === "end") {
                eventSource.close();
                btnRun.disabled = false;
                btnRun.querySelector(".btn-text").textContent = "Execute Autonomously";
                loopStatus.textContent = "COMPLETED";
                loopStatus.className = "badge-status success";
            }
        };

        eventSource.onerror = (err) => {
            console.error("SSE Error:", err);
            eventSource.close();
            btnRun.disabled = false;
            btnRun.querySelector(".btn-text").textContent = "Execute Autonomously";
            loopStatus.textContent = "DONE";
        };
    }

    function renderPlan(steps) {
        planContainer.innerHTML = "";
        document.getElementById("plan-count").textContent = `${steps.length} Steps`;

        steps.forEach(s => {
            const div = document.createElement("div");
            div.className = `step-item ${s.status}`;
            div.innerHTML = `
                <div class="step-top">
                    <span class="step-num">Step ${s.step_id}</span>
                    <span class="step-tool">${s.tool_name}</span>
                </div>
                <div class="step-desc">${s.description}</div>
                <div class="step-args">${JSON.stringify(s.tool_args)}</div>
            `;
            planContainer.appendChild(div);
        });
    }

    function renderMemory(scratchpad) {
        const entities = scratchpad.entities || {};
        entitiesList.innerHTML = "";

        const keys = Object.keys(entities);
        if (keys.length === 0) {
            entitiesList.innerHTML = `<span class="empty-text">No entities extracted yet.</span>`;
        } else {
            keys.forEach(k => {
                const row = document.createElement("div");
                row.className = "entity-row";
                row.innerHTML = `<span class="entity-k">${k}</span><span class="entity-v">${entities[k]}</span>`;
                entitiesList.appendChild(row);
            });
        }

        stepResultsList.textContent = JSON.stringify(scratchpad.step_results || {}, null, 2);
    }

    function renderVerification(v) {
        const pct = Math.round((v.confidence_score || 0) * 100);
        verifScore.textContent = `${pct}%`;

        if (v.is_verified) {
            verifMeter.classList.add("verified");
            verifBadge.textContent = "VERIFIED";
            verifBadge.className = "badge-status success";
            verifStatusTitle.textContent = "Outcome Confirmed";
            verifStatusDesc.textContent = "System state matches user goal assertions.";
        } else {
            verifBadge.textContent = "FAILED";
            verifBadge.className = "badge-status";
            verifStatusTitle.textContent = "Discrepancies Found";
            verifStatusDesc.textContent = v.discrepancies ? v.discrepancies.join(", ") : "Could not verify outcome.";
        }

        verifChecklist.innerHTML = "";
        (v.checks_performed || []).forEach(c => {
            const li = document.createElement("li");
            li.innerHTML = `&check; ${c}`;
            verifChecklist.appendChild(li);
        });

        if (v.evidence) {
            verifEvidence.textContent = `Evidence: ${v.evidence}`;
        }
    }

    function renderEvidencePacket(packet) {
        evidenceSummary.textContent = packet.summary;
        statActions.textContent = packet.total_actions_taken;
        statTime.textContent = `${packet.execution_time_seconds}s`;
        statDiff.textContent = packet.state_diffs ? (packet.state_diffs.total_new_invoices || 0) : 0;
        evidenceBanner.classList.remove("hidden");
    }
});
