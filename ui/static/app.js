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
    quotation: "Get me the quotation for the latest deal signed.",
    missing_quotation:
      "Get the quotation for the latest signed deal with OmniCorp.",
    company_search: "Search company records for Acme.",
  };
  const terminal = new Set([
    "completed",
    "failed",
    "partially_completed",
    "interrupted",
  ]);
  function keepExpanded(detail) {
    if (!detail) return detail;
    detail.open = true;
    const summary = detail.querySelector(":scope > summary");
    if (summary && !summary.dataset.expandedLock) {
      summary.dataset.expandedLock = "true";
      summary.title = "This information stays visible while you work";
      summary.addEventListener("click", (event) => event.preventDefault());
    }
    return detail;
  }
  document
    .querySelectorAll("details[data-always-open]")
    .forEach(keepExpanded);
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
    deal_id: "Signed deal",
    customer_name: "Customer",
    signed_at: "Signed on",
    quotation_id: "Quotation",
    quotation_amount: "Quoted amount",
    quotation_currency: "Currency",
    quote_valid_until: "Valid until",
    matched_resources: "Matches found",
  };
  let source = null,
    currentRun = null,
    currentApproval = null,
    busy = false,
    lastMemory = null,
    lastPacket = null,
    clearHistoryTimer = null,
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
    const waitingForReply = value && !currentApproval;
    $("btn-run").disabled = waitingForReply;
    $("btn-preview").disabled = value;
    $("btn-reset-erp").disabled = value;
    $("btn-new-chat").disabled = value;
    $("btn-clear-history").disabled = value;
    $("task-input").disabled = waitingForReply;
    $("example-select").disabled = waitingForReply;
  }
  function outcomeLabel(packet) {
    return packet.status === "failed" && packet.issue
      ? packet.issue.title
      : labels[packet.status] || packet.status;
  }
  function runErrorMessage(run) {
    return run.status === "interrupted"
      ? "The server restarted before this task finished. Review the ledger and start the task again."
      : "The worker stopped before producing a checked result. Review the activity and any saved changes before trying again.";
  }
  function setStatus(status) {
    $("run-status").textContent =
      status === "failed" && lastPacket
        ? outcomeLabel(lastPacket)
        : labels[status] || status;
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
    currentApproval = run.approval || null;
    lastMemory = run.scratchpad || null;
    lastPacket = run.packet || null;
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
    if (run.packet) {
      renderChat(run.packet, false);
      renderWhiteboard(run.scratchpad, run.packet, false);
    } else if (!terminal.has(run.status)) {
      renderChat(null, true);
      renderWhiteboard(run.scratchpad, null, true);
    } else {
      renderChat(
        {
          run_id: run.id,
          task: run.task,
          mode: run.mode,
          status: run.status,
          summary: runErrorMessage(run),
        },
        false,
      );
      renderWhiteboard(null, null, false);
    }
    setStatus(run.status);
    setBusy(!terminal.has(run.status));
    notice(run.error ? runErrorMessage(run) : "");
  }
  const conversationStorageKey = "operon.conversation.v1";
  const welcomeMessage =
    "Hi, I’m Operon. What can I help you get done? I can find company documents, check quotations, process invoices, and work with the sandbox ledger. I’ll keep you posted and show you what I verified.";
  let conversation = [],
    contextRunId = null,
    pendingMessageId = null;

  function messageRecord(role, text, runId = null, status = "completed") {
    return { id: crypto.randomUUID(), role, text, runId, status };
  }
  function persistConversation() {
    try {
      localStorage.setItem(
        conversationStorageKey,
        JSON.stringify({ messages: conversation.slice(-100), contextRunId }),
      );
    } catch (_) {
      /* The current conversation still works if browser storage is full. */
    }
  }
  function restoreConversation() {
    try {
      const saved = JSON.parse(localStorage.getItem(conversationStorageKey));
      if (
        !saved ||
        !Array.isArray(saved.messages) ||
        !saved.messages.every(
          (m) =>
            m &&
            typeof m.id === "string" &&
            typeof m.text === "string" &&
            ["user", "assistant"].includes(m.role),
        )
      )
        return false;
      conversation = saved.messages.slice(-100);
      contextRunId =
        typeof saved.contextRunId === "string" ? saved.contextRunId : null;
      return true;
    } catch (_) {
      return false;
    }
  }
  function renderTranscript(forceLatest = false) {
    const thread = $("chat-thread");
    const oldTop = thread.scrollTop;
    const follow =
      forceLatest || thread.scrollHeight - oldTop - thread.clientHeight < 32;
    thread.replaceChildren(
      ...conversation.map((message) => {
        const turn = element(
          "article",
          "chat-turn " +
            (message.role === "user"
              ? "chat-turn-request"
              : "chat-turn-response"),
        );
        turn.dataset.messageId = message.id;
        turn.append(
          element(
            "span",
            "chat-turn-author",
            message.role === "user" ? "You" : "Operon",
          ),
          element("p", "chat-message", message.text),
        );
        return turn;
      }),
    );
    requestAnimationFrame(() => {
      thread.scrollTop = follow ? thread.scrollHeight : oldTop;
      updateChatScroll();
    });
    persistConversation();
  }
  function addMessage(role, text, runId = null, status = "completed") {
    const message = messageRecord(role, text, runId, status);
    conversation.push(message);
    conversation = conversation.slice(-100);
    renderTranscript(true);
    return message;
  }
  function updateMessage(message, text, status = "completed") {
    message.text = text;
    message.status = status;
    renderTranscript();
  }
  function renderChat(packet, isWorking) {
    const runId = packet ? packet.run_id : currentRun && currentRun.id;
    let response = [...conversation]
      .reverse()
      .find((m) => m.role === "assistant" && m.runId === runId && runId);
    if (!response && pendingMessageId)
      response = conversation.find((m) => m.id === pendingMessageId);
    if (!response)
      response = addMessage(
        "assistant",
        "Working on your request…",
        runId,
        "working",
      );
    response.runId = runId;
    if (isWorking) {
      const waiting = Boolean(currentApproval);
      $("chat-badge").textContent = waiting ? "Needs approval" : "Working…";
      $("chat-badge").className = "chat-badge working";
      updateMessage(
        response,
        waiting
          ? "I’ve reached an action that needs your approval. The details are shown below—reply ‘approve’ or ‘decline’, or use the buttons."
          : "Got it. I’m checking the company sources and working on that now.",
        "working",
      );
      return;
    }
    if (!packet) return;
    const ok = packet.status === "completed";
    $("chat-badge").textContent = ok
      ? packet.mode === "preview"
        ? "Preview complete"
        : "Completed"
      : outcomeLabel(packet);
    $("chat-badge").className = "chat-badge" + (ok ? "" : " failed");
    updateMessage(
      response,
      packet.agent_message || packet.summary,
      packet.status,
    );
  }
  function updateChatScroll() {
    const thread = $("chat-thread");
    $("btn-chat-latest").classList.toggle(
      "hidden",
      thread.scrollHeight - thread.scrollTop - thread.clientHeight < 32,
    );
  }
  $("chat-thread").addEventListener("scroll", updateChatScroll, {
    passive: true,
  });
  window.addEventListener("resize", updateChatScroll);
  $("btn-chat-latest").addEventListener("click", () => {
    $("chat-thread").scrollTop = $("chat-thread").scrollHeight;
    $("chat-thread").focus({ preventScroll: true });
    updateChatScroll();
  });
  function clearConversation() {
    if (busy || currentApproval) return;
    if (source) source.close();
    currentRun = null;
    contextRunId = null;
    pendingMessageId = null;
    lastMemory = null;
    lastPacket = null;
    conversation = [messageRecord("assistant", welcomeMessage)];
    $("task-input").value = "";
    $("approval-panel").classList.add("hidden");
    $("evidence-banner").classList.add("hidden");
    $("preview-note").classList.add("hidden");
    $("recovery-note").classList.add("hidden");
    $("run-caption").textContent = "Start with a request or a question.";
    $("plan-container").replaceChildren(
      element("li", "muted", "The next task’s plan will appear here."),
    );
    $("plan-count").textContent = "0 steps";
    $("entities-list").replaceChildren(
      element("p", "muted", "Details appear as source files are read."),
    );
    $("fact-count").textContent = "0";
    $("source-list").replaceChildren(
      element("li", "muted", "No documents read yet."),
    );
    $("verification-symbol").textContent = "○";
    $("verif-title").textContent = "Waiting for a task";
    $("verif-description").textContent =
      "The result is checked against the source and ledger.";
    $("verif-checklist").replaceChildren();
    $("verif-evidence").textContent = "";
    $("chat-badge").textContent = "Ready";
    $("chat-badge").className = "chat-badge";
    setStatus("Ready");
    renderWhiteboard(null, null, false);
    renderTranscript(true);
    localStorage.removeItem("operon.lastRun");
    $("task-input").focus();
  }
  $("btn-new-chat").addEventListener("click", clearConversation);
  function renderWhiteboard(memory, packet, isWorking) {
    if (memory) lastMemory = memory;
    if (packet) lastPacket = packet;
    const mem = memory || lastMemory || {};
    const pack = packet || lastPacket || null;

    const goalEl = $("wb-task-goal");
    if (goalEl) {
      const taskVal =
        currentRun && currentRun.task
          ? currentRun.task
          : $("task-input").value.trim();
      goalEl.textContent = taskVal || "Awaiting task description…";
    }

    const badge = $("wb-status-badge");
    if (badge) {
      if (isWorking) {
        badge.textContent = "Working…";
        badge.className = "wb-status-badge working";
      } else if (pack) {
        const ok = pack.status === "completed";
        badge.textContent = ok
          ? pack.mode === "preview"
            ? "Preview complete"
            : "Completed"
          : outcomeLabel(pack);
        badge.className = "wb-status-badge " + (ok ? "completed" : "failed");
      } else {
        badge.textContent = "Ready";
        badge.className = "wb-status-badge";
      }
    }

    const grid = $("wb-facts-grid");
    if (grid) {
      grid.replaceChildren();
      const facts = Object.entries(mem.entities || {}).filter(
        ([k]) => factLabels[k],
      );
      if (!facts.length) {
        const empty = element("div", "wb-fact-row wb-facts-empty");
        empty.append(
          element("dt", "sr-only", "Collected facts"),
          element(
            "dd",
            "wb-empty-hint",
            isWorking
              ? "Reading source details…"
              : pack && pack.issue
                ? "No source facts were confirmed for this task."
                : "Facts appear as source files are read.",
          ),
        );
        grid.append(empty);
      } else {
        facts.forEach(([key, val]) => {
          const tag = element("div", "wb-fact-row");
          const label = factLabels[key] || key;
          const displayVal = ["amount", "quotation_amount"].includes(key)
            ? Number(val).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })
            : String(val);
          tag.append(element("dt", "", label), element("dd", "", displayVal));
          grid.append(tag);
        });
      }
    }

    const sourceLinks = $("wb-source-links");
    sourceLinks.replaceChildren();
    const capturedSources =
      (pack && pack.source_documents) || mem.source_documents || [];
    if (pack && capturedSources.length) {
      capturedSources.forEach((doc, index) => {
        const link = element(
          "a",
          "",
          doc.file_path.split(/[\\/]/).slice(-2).join("/"),
        );
        link.href = `/api/runs/${pack.run_id}/sources/${index}`;
        link.target = "_blank";
        link.rel = "noopener";
        link.title =
          "Open the captured source; its hash is checked before serving.";
        const item = element("li");
        item.append(link);
        sourceLinks.append(item);
      });
    } else {
      sourceLinks.append(
        element(
          "li",
          "wb-empty-hint",
          pack
            ? "No source documents were captured."
            : "Source links appear after the task finishes.",
        ),
      );
    }

    const notesList = $("wb-notes-list");
    if (notesList) {
      notesList.replaceChildren();
      const notes = mem.notes || [];
      if (!notes.length) {
        notesList.append(
          element(
            "li",
            "wb-empty-hint",
            isWorking
              ? "Waiting for the next task update…"
              : "Notes appear as the task progresses.",
          ),
        );
      } else {
        notes.forEach((note) => {
          notesList.append(element("li", "wb-note-item", note));
        });
        notesList.scrollTop = notesList.scrollHeight;
      }
    }

    const cardResult = $("wb-card-result");
    const stamp = $("wb-result-stamp");
    const msg = $("wb-result-message");
    const stats = $("wb-result-stats");

    if (cardResult && stamp && msg && stats) {
      if (isWorking && !pack) {
        cardResult.className = "wb-card wb-card-result";
        stamp.textContent = "In progress";
        stamp.className = "wb-stamp-badge working";
        msg.textContent =
          "The outcome will appear after the source and ledger checks finish.";
        stats.classList.add("hidden");
      } else if (pack) {
        const ok = pack.status === "completed";
        cardResult.className = "wb-card wb-card-result" + (ok ? "" : " failed");
        stamp.textContent = ok ? "Verified" : outcomeLabel(pack);
        stamp.className = "wb-stamp-badge" + (ok ? " verified" : " failed");
        msg.textContent = pack.agent_message || pack.summary;
        stats.classList.remove("hidden");
        const statusEl = $("wb-stat-status");
        if (statusEl)
          statusEl.textContent = ok ? "Verified" : outcomeLabel(pack);
        const ledgerEl = $("wb-stat-ledger");
        if (ledgerEl) {
          const count = (pack.created_records || []).length;
          ledgerEl.textContent = count
            ? `${count} ${pack.mode === "preview" ? "proposed" : "new"} record${count === 1 ? "" : "s"}`
            : "No new records";
        }
        const hashEl = $("wb-stat-hash");
        if (hashEl)
          hashEl.textContent =
            pack.verification && pack.verification.is_verified
              ? "Checks passed"
              : "Review report";
      } else {
        cardResult.className = "wb-card wb-card-result";
        stamp.textContent = "Pending";
        stamp.className = "wb-stamp-badge";
        msg.textContent = "Run a task to see the checked outcome here.";
        stats.classList.add("hidden");
      }
    }
  }
  async function start(mode) {
    const task = $("task-input").value.trim();
    if (!task || (busy && !currentApproval)) return;
    notice("");
    const userMessage = addMessage("user", task);
    const responseMessage = addMessage(
      "assistant",
      "Got it—I’m checking that now…",
      null,
      "working",
    );
    pendingMessageId = responseMessage.id;
    $("task-input").value = "";
    setBusy(true);
    try {
      const response = await post("/api/chat", {
        task,
        mode,
        context_run_id: contextRunId,
      });
      if (response.kind === "reply") {
        updateMessage(responseMessage, response.reply);
        pendingMessageId = null;
        $("chat-badge").textContent = currentApproval
          ? "Needs approval"
          : "Ready";
        $("chat-badge").className =
          "chat-badge" + (currentApproval ? " working" : "");
        setBusy(Boolean(currentApproval));
        $("task-input").focus();
        return;
      }
      contextRunId = response.run.id;
      userMessage.runId = response.run.id;
      responseMessage.runId = response.run.id;
      persistConversation();
      await openRun(response.run.id, { keepConversation: true });
    } catch (error) {
      updateMessage(
        responseMessage,
        "I couldn’t complete that request: " + error.message,
        "failed",
      );
      pendingMessageId = null;
      notice(error.message);
      setBusy(Boolean(currentApproval));
      $("task-input").value = task;
    }
  }
  async function openRun(id, { keepConversation = false } = {}) {
    if (source) source.close();
    try {
      const run = await api(`/api/runs/${id}`);
      contextRunId = run.id;
      if (!keepConversation) {
        conversation = [
          messageRecord("assistant", welcomeMessage),
          messageRecord("user", run.task, run.id),
          messageRecord(
            "assistant",
            "Loading the task result…",
            run.id,
            "working",
          ),
        ];
        pendingMessageId = conversation[conversation.length - 1].id;
        renderTranscript(true);
      }
      reset(run);
      localStorage.setItem("operon.lastRun", id);
      persistConversation();
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
    if (event.event === "start") {
      currentRun.status = "running";
      setStatus("running");
      if (!lastPacket) renderChat(null, true);
    }
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
      currentRun.status = "waiting_approval";
      $("approval-title").textContent = currentApproval.data_classification
        ? `Review ${currentApproval.data_classification.toLowerCase()} access`
        : "This action needs approval";
      $("approval-risk").textContent =
        `${currentApproval.risk_level || "MEDIUM"} risk`;
      $("approval-classification").textContent =
        currentApproval.data_classification || "Protected action";
      $("approval-resource").textContent =
        currentApproval.resource || currentApproval.tool_name;
      $("approval-reason").textContent =
        currentApproval.reason || "This action falls outside the autonomous policy.";
      $("approval-scope").textContent =
        currentApproval.approval_scope === "all_modes"
          ? "This exact access, once · applies to previews too"
          : "This exact action, once";
      $("approval-prompt").textContent = currentApproval.prompt;
      $("approval-args").textContent = JSON.stringify(
        currentApproval.tool_args,
        null,
        2,
      );
      $("approval-panel").classList.remove("hidden");
      setStatus("waiting_approval");
      setBusy(true);
      renderChat(null, true);
      $("btn-approve").disabled = false;
      $("btn-reject").disabled = false;
      loadHistory().catch((error) => notice(error.message));
    } else if (event.event === "approval_decision") {
      currentApproval = null;
      currentRun.status = "running";
      $("approval-panel").classList.add("hidden");
      setStatus("running");
      setBusy(true);
      renderChat(null, true);
    } else if (event.event === "error") {
      const message = event.user_message || runErrorMessage(currentRun);
      notice(message);
      renderChat(
        {
          run_id: currentRun.id,
          task: currentRun.task,
          status: "failed",
          summary: message,
        },
        false,
      );
    } else if (event.event === "end") {
      source.close();
      currentApproval = null;
      currentRun.status = event.status;
      pendingMessageId = null;
      setBusy(false);
      setStatus(event.status);
      $("approval-panel").classList.add("hidden");
      loadHistory().catch((error) => notice(error.message));
      loadLedger();
      persistConversation();
    }
  }
  function renderPlan(steps) {
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
      detail.open = true;
      detail.dataset.alwaysOpen = "";
      detail.append(
        element("summary", "", "View action details"),
        element(
          "pre",
          "",
          `${step.tool_name}\n${JSON.stringify(step.tool_args, null, 2)}${step.error ? "\n\n" + step.error : ""}`,
        ),
      );
      keepExpanded(detail);
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
          ["amount", "quotation_amount"].includes(key)
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
    renderWhiteboard(
      memory,
      null,
      currentRun ? currentRun.status === "running" : true,
    );
  }
  function renderSources(sources) {
    $("source-list").replaceChildren();
    sources.forEach((doc) => {
      const row = element("li", "", doc.file_path.split(/[\\/]/).pop());
      const hash = element(
        "small",
        "",
        `${doc.data_classification ? doc.data_classification + " · " : ""}SHA-256 · ${doc.sha256.slice(0, 20)}…`,
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
    lastPacket = packet;
    const ok = packet.status === "completed";
    $("evidence-banner").className = "report-panel" + (ok ? "" : " failed");
    $("report-title").textContent =
      packet.mode === "preview"
        ? ok
          ? "Preview verified"
          : packet.issue
            ? `Preview: ${packet.issue.title.toLowerCase()}`
            : "Preview needs attention"
        : ok
          ? "Outcome verified"
          : packet.issue
            ? packet.issue.title
            : "Task needs attention";
    $("evidence-summary-text").textContent = packet.summary;
    $("stat-actions").textContent = packet.total_actions_taken;
    $("stat-time").textContent = `${packet.execution_time_seconds}s`;
    $("stat-diff").textContent = packet.created_records.length;
    const policyChecks = packet.policy_checks || [];
    const approvedChecks = policyChecks.filter(
      (check) => check.decision === "approved",
    ).length;
    const declinedChecks = policyChecks.filter(
      (check) => check.decision === "declined",
    ).length;
    $("policy-summary").textContent = policyChecks.length
      ? packet.mode === "preview"
        ? `${policyChecks.length} protected action${policyChecks.length === 1 ? "" : "s"} identified${approvedChecks ? ` · ${approvedChecks} approved access` : ""}`
        : `${policyChecks.length} protected action${policyChecks.length === 1 ? "" : "s"} reviewed · ${declinedChecks ? `${declinedChecks} declined` : `${approvedChecks} approved`}`
      : "Within approval policy";
    $("state-diff").textContent = JSON.stringify(packet.state_diffs, null, 2);
    $("evidence-digest").textContent =
      `Evidence SHA-256: ${packet.evidence_sha256}`;
    $("download-evidence").href = `/api/runs/${packet.run_id}/evidence`;
    renderSources(packet.source_documents);
    renderChat(packet, false);
    renderWhiteboard(null, packet, false);
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
            (run.status === "failed" && run.issue_title
              ? run.issue_title
              : labels[run.status] || run.status),
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
    $("btn-clear-history").disabled = busy || !runs.length;
    return runs;
  }

  function resetClearHistoryButton() {
    if (clearHistoryTimer) clearTimeout(clearHistoryTimer);
    clearHistoryTimer = null;
    $("btn-clear-history").textContent = "Clear";
    $("btn-clear-history").classList.remove("confirming");
  }

  async function clearSavedHistory() {
    const button = $("btn-clear-history");
    if (busy || button.disabled) return;
    if (!button.classList.contains("confirming")) {
      button.textContent = "Confirm clear";
      button.classList.add("confirming");
      clearHistoryTimer = setTimeout(resetClearHistoryButton, 5000);
      return;
    }
    resetClearHistoryButton();
    button.disabled = true;
    try {
      const result = await api("/api/runs", { method: "DELETE" });
      clearConversation();
      await loadHistory();
      notice(
        result.deleted_runs
          ? `Cleared ${result.deleted_runs} saved task${result.deleted_runs === 1 ? "" : "s"} and this conversation.`
          : "There was no saved history to clear.",
      );
    } catch (error) {
      notice(error.message);
      button.disabled = false;
    }
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
  $("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    start("execute");
  });
  $("task-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $("chat-form").requestSubmit();
    }
  });
  $("btn-preview").addEventListener("click", () => start("preview"));
  $("btn-approve").addEventListener("click", () => decide(true));
  $("btn-reject").addEventListener("click", () => decide(false));
  $("example-select").addEventListener("change", (event) => {
    if (examples[event.target.value]) {
      $("task-input").value = examples[event.target.value];
      $("task-input").focus();
    }
  });
  $("btn-refresh-erp").addEventListener("click", loadLedger);
  $("btn-refresh-history").addEventListener("click", () =>
    loadHistory().catch((error) => notice(error.message)),
  );
  $("btn-clear-history").addEventListener("click", clearSavedHistory);
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
  const copyBtn = $("btn-copy-whiteboard");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const task = $("wb-task-goal") ? $("wb-task-goal").textContent : "";
      const facts = Array.from(
        document.querySelectorAll(
          "#wb-facts-grid .wb-fact-row:not(.wb-facts-empty)",
        ),
      )
        .map((row) =>
          Array.from(row.children)
            .map((cell) => cell.textContent)
            .join(": "),
        )
        .join("\n");
      const notes = Array.from(
        document.querySelectorAll("#wb-notes-list .wb-note-item"),
      )
        .map((n) => "- " + n.textContent)
        .join("\n");
      const result = $("wb-result-message")
        ? $("wb-result-message").textContent
        : "";
      const text = `Operon scratchpad\n\nTask\n${task}\n\nCollected facts\n${facts || "None"}\n\nWorking notes\n${notes || "None"}\n\nOutcome\n${result}`;
      navigator.clipboard
        .writeText(text)
        .then(() => {
          copyBtn.textContent = "Copied";
          $("wb-copy-status").textContent = "Scratchpad notes copied.";
          setTimeout(() => {
            copyBtn.textContent = "Copy notes";
          }, 2000);
        })
        .catch(() => {
          $("wb-copy-status").textContent =
            "Could not copy the notes. Please try again.";
        });
    });
  }
  const restoredConversation = restoreConversation();
  if (!conversation.length)
    conversation = [messageRecord("assistant", welcomeMessage)];
  renderTranscript(true);
  renderWhiteboard(null, null, false);
  api("/api/info")
    .then((info) => ($("model-name").textContent = info.model_name))
    .catch((error) => notice(error.message));
  loadLedger();
  loadHistory()
    .then((runs) => {
      const active = runs.find((run) => !terminal.has(run.status));
      const saved = localStorage.getItem("operon.lastRun");
      if (active)
        return openRun(active.id, {
          keepConversation: contextRunId === active.id,
        });
      if (contextRunId && runs.some((run) => run.id === contextRunId))
        return openRun(contextRunId, { keepConversation: true });
      if (
        !restoredConversation &&
        saved &&
        runs.some((run) => run.id === saved)
      )
        return openRun(saved);
      contextRunId = null;
      persistConversation();
    })
    .catch((error) => notice(error.message));
});
