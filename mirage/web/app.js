"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { report: null, status: null, markets: [], selected: null, drawerMarket: null, scanning: false, poll: null, previewToken: 0, lastFocus: null };
  const KNOWN = {
    "0x8eaf7b29f02ba8d8c1d7aeb587403dcb16e2e943e4e2f5f94b0963c2386406c9": "PAXG",
    "0xbd1ad3b968f5f0552dbd8cf1989a62881407c5cccf9e49fb3657c8731caf0c1f": "deUSD"
  };
  const SEVERITY = { block: "Blocked", insufficient: "Insufficient", warn: "Warning", pass: "Passed", unknown: "Unknown" };
  const ORDER = { block: 4, insufficient: 3, warn: 2, pass: 1, unknown: 0 };
  const ACCOUNTING = new Set(["invalid_market_state", "market_not_created", "accounting_invariant_broken", "no_free_liquidity", "elevated_share_exchange_rate", "accounting_observed"]);

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }
  function safeSeverity(value) { return Object.hasOwn(SEVERITY, value) ? value : "unknown"; }
  function severityBadge(value, label) { const kind = safeSeverity(value); return node("span", `severity severity-${kind}`, label || SEVERITY[kind]); }
  function shortHex(value, lead = 8, tail = 4) { return typeof value === "string" && value.length > lead + tail + 2 ? `${value.slice(0, lead + 2)}…${value.slice(-tail)}` : value || "—"; }
  function grouped(value) { return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  function usdc(raw, fraction = 2) {
    if (raw === undefined || raw === null || !/^-?\d+$/.test(String(raw))) return "—";
    try {
      const value = BigInt(raw), sign = value < 0n ? "−" : "", absolute = value < 0n ? -value : value;
      const whole = absolute / 1000000n, remainder = String(absolute % 1000000n).padStart(6, "0");
      const digits = fraction === 6 ? remainder : remainder.slice(0, fraction);
      if (absolute > 0n && absolute < 10000n && fraction === 2) return `${sign}<0.01`;
      return sign + grouped(whole) + (fraction ? `.${digits}` : "");
    } catch { return "—"; }
  }
  function ratio(value) {
    if (value === undefined || value === null || !/^-?\d+(\.\d+)?$/.test(String(value))) return "—";
    const parts = String(value).split(".");
    return `${grouped(parts[0])}${parts[1] ? "." + parts[1].slice(0, 2).padEnd(2, "0") : ""}×`;
  }
  function percentage(value) { const parsed = Number(value); return value !== null && value !== undefined && Number.isFinite(parsed) ? `${(parsed * 100).toFixed(2)}%` : "—"; }
  function marketName(market) { return market?.display?.collateral_symbol || KNOWN[market?.market_id?.toLowerCase()] || shortHex(market?.market_id, 5, 4); }
  function loanName(market) { return market?.display?.loan_symbol || "USDC"; }
  function metricValues(market) { return Object.assign({}, ...(market?.findings || []).map((finding) => finding.metrics || {})); }
  function reportLive() { return state.report?.source?.kind === "the-graph" && state.report?.capture_mode === "live"; }
  function reportBlock() { return state.report?.block_number; }
  function utcTime(timestamp) { const value = Number(timestamp); if (timestamp === undefined || timestamp === null || !Number.isFinite(value)) return null; const date = new Date(value * 1000); return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 16).replace("T", " ") + " UTC"; }
  function validId(id) { return typeof id === "string" && /^0x[0-9a-fA-F]{64}$/.test(id); }
  function showNotice(message, retry = false) { $("notice-message").textContent = message; $("retry-button").hidden = !retry; $("notice").hidden = false; }
  function hideNotice() { $("notice").hidden = true; }
  function toast(message) { $("toast").textContent = message; $("toast").hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { $("toast").hidden = true; }, 2200); }
  async function copy(value) { try { await navigator.clipboard.writeText(value); toast("Copied to clipboard"); } catch { toast("Copy unavailable. Select the evidence text instead."); } }
  async function api(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(url, { cache: "no-store", signal: controller.signal, ...options });
      let payload;
      try { payload = await response.json(); } catch { throw new Error("The server returned an unreadable response."); }
      if (!response.ok) throw new Error(typeof payload?.error === "string" ? payload.error : typeof payload?.message === "string" ? payload.message : `Request failed (${response.status}).`);
      return payload;
    } catch (error) { if (error.name === "AbortError") throw new Error("The request timed out. Check the local server and retry."); throw error; }
    finally { clearTimeout(timer); }
  }

  function renderProvenance() {
    const report = state.report;
    if (!report) return;
    const graph = report.source?.kind === "the-graph", live = reportLive();
    const blockLabel = report.block_number !== undefined && report.block_number !== null ? grouped(report.block_number) : "not supplied";
    const timestamp = utcTime(report.block_timestamp);
    $("source-label").textContent = live ? "Live capture complete" : "Saved evidence";
    $("origin-label").textContent = graph ? "The Graph" : "Direct RPC";
    const discoveryCount = report.source?.discovery_market_count;
    $("origin-note").textContent = graph && discoveryCount !== undefined ? `${grouped(discoveryCount)} discovered; ${grouped(state.markets.length)} inspected` : graph ? "Graph discovery at the recorded block" : "Fixed-block chain observations";
    $("source-description").textContent = live
      ? `Block ${blockLabel}${timestamp ? ` / ${timestamp}` : ""}. Captured in this run; refresh to check again.`
      : `Saved ${graph ? "Graph-discovered" : "chain"} observations. Block ${blockLabel}${timestamp ? ` / ${timestamp}` : ""}. Refresh for a new check.`;
  }
  function renderReport() {
    const report = state.report;
    const count = state.markets.length;
    const blocked = state.markets.filter((m) => m.severity === "block").length;
    const insufficient = state.markets.filter((m) => m.severity === "insufficient").length;
    $("market-count").textContent = grouped(count);
    $("restricted-count").textContent = `${grouped(blocked)} / ${grouped(insufficient)}`;
    $("block-number").textContent = report.block_number !== undefined ? grouped(report.block_number) : "—";
    $("copy-block").disabled = !report.block_hash;
    $("copy-block").title = report.block_hash || "Block hash unavailable";
    renderProvenance();
    const pending = state.markets.some((m) => (m.findings || []).some((f) => f.code === "remaining_checks_pending"));
    const oracleFindings = state.markets.flatMap((m) => (m.findings || []).filter((f) => detectorType(f) === "oracle"));
    const depthFindings = state.markets.flatMap((m) => (m.findings || []).filter((f) => detectorType(f) === "depth"));
    $("oracle-coverage").textContent = oracleFindings.length ? "Inspect each market's result" : pending ? "Not included in this report" : "No oracle evidence in this report";
    $("depth-coverage").textContent = depthFindings.length ? "Inspect each market's result" : pending ? "Not included in this report" : "No exit-depth evidence in this report";
    const select = $("allocation-market");
    const previous = state.selected;
    select.replaceChildren();
    for (const market of state.markets) {
      const option = node("option", null, `${marketName(market)} / ${loanName(market)} — ${SEVERITY[safeSeverity(market.severity)]}`);
      option.value = market.market_id;
      select.append(option);
    }
    if (!count) { const option = node("option", null, "No markets available"); option.value = ""; select.append(option); }
    state.selected = state.markets.some((m) => m.market_id === previous) ? previous : state.markets[0]?.market_id || null;
    select.value = state.selected || "";
    $("evaluate-button").disabled = !state.selected;
    if (!state.scanning) $("scan-button").querySelector("span").textContent = state.selected ? "Check market" : "Refresh evidence";
    renderMarkets();
  }

  function renderMarkets() {
    const term = $("market-search").value.trim().toLowerCase();
    const filter = $("risk-filter").value;
    const list = state.markets.filter((market) => {
      const searchable = [market.market_id, marketName(market), loanName(market), market.display?.oracle_address].join(" ").toLowerCase();
      return (!term || searchable.includes(term)) && (filter === "all" || market.severity === filter);
    });
    $("visible-count").textContent = state.report ? `${list.length} of ${state.markets.length}` : "No report";
    const body = $("market-body"); body.replaceChildren();
    for (const market of list) {
      const metrics = metricValues(market), row = node("tr", market.market_id === state.selected ? "is-selected" : "");
      const nameCell = node("td"), name = node("div", "market-name");
      name.append(node("span", "token-emblem", marketName(market).slice(0, 1)));
      const nameText = node("div"), primary = node("div", "market-primary", marketName(market));
      primary.append(node("span", "market-loan", ` / ${loanName(market)}`));
      nameText.append(primary, node("span", "market-secondary", shortHex(market.market_id, 5, 4))); name.append(nameText); nameCell.append(name);
      const admission = node("td"); admission.append(severityBadge(market.severity));
      const liquidity = node("td", `number market-value${String(metrics.available_liquidity_raw) === "0" ? " value-zero" : ""}`, usdc(metrics.available_liquidity_raw));
      liquidity.title = `${usdc(metrics.available_liquidity_raw, 6)} USDC available at this block`;
      const share = node("td", "number rate-value", ratio(metrics.share_price_multiple_vs_initial));
      const actionCell = node("td"), inspect = node("button", "market-chevron", "›");
      inspect.type = "button"; inspect.setAttribute("aria-label", `Inspect ${marketName(market)} market evidence`); inspect.title = "Inspect evidence";
      inspect.addEventListener("click", (event) => { event.stopPropagation(); openDrawer(market, inspect); });
      actionCell.append(inspect); row.append(nameCell, admission, liquidity, share, actionCell);
      row.addEventListener("click", () => openDrawer(market, inspect)); body.append(row);
    }
    $("table-empty").hidden = list.length > 0;
    if (state.report && list.length === 0) {
      $("empty-title").textContent = state.markets.length ? "No markets match this view" : "This report contains no markets";
      $("empty-description").textContent = state.markets.length ? "Try another search or choose all verdicts." : "Run a live scan to request market evidence.";
    }
  }

  function detectorType(finding) {
    const code = String(finding.code || "").toLowerCase();
    if (code === "remaining_checks_pending") return "pending";
    if (ACCOUNTING.has(code) || code.includes("accounting") || code.includes("share_exchange") || code.includes("free_liquidity")) return "accounting";
    if (/exit|depth|liquidation|slippage/.test(code)) return "depth";
    if (/oracle|frozen|price|reference/.test(code)) return "oracle";
    return "other";
  }
  function detectorCard(title, findings, missing) {
    const card = node("section", "detector-card"), head = node("div", "detector-heading");
    const worst = findings.reduce((value, f) => (ORDER[safeSeverity(f.severity)] > ORDER[value] ? safeSeverity(f.severity) : value), "unknown");
    head.append(node("h3", null, title), findings.length ? severityBadge(worst) : severityBadge("insufficient", "Pending"));
    card.append(head);
    if (!findings.length) card.append(node("p", null, missing));
    for (const finding of findings) {
      const item = node("div", "detector-finding");
      item.append(node("strong", null, finding.summary || finding.code || "Finding"));
      if (finding.code) item.append(node("p", null, finding.code));
      const metrics = Object.entries(finding.metrics || {}).filter(([key]) => !["unit", "principal"].includes(key));
      if (metrics.length) {
        const details = node("details", "measurement-details"), values = node("dl", "detector-metrics");
        details.append(node("summary", null, `Inspect measurements (${metrics.length})`));
        for (const [key, value] of metrics) {
          const output = node("dd");
          if (value !== null && typeof value === "object") output.append(node("pre", "measurement-object", JSON.stringify(value, null, 2)));
          else output.textContent = value === null ? "Unknown" : String(value);
          values.append(node("dt", null, key.replaceAll("_", " ")), output);
        }
        details.append(values); item.append(details);
      }
      card.append(item);
    }
    return card;
  }
  function evidenceOf(market) {
    const seen = new Set(), items = [];
    const groups = [...(market.findings || []), market.rate || {}];
    for (const finding of groups) for (const evidence of finding.evidence || []) {
      const text = JSON.stringify(evidence);
      if (!seen.has(text)) { seen.add(text); items.push(evidence); }
    }
    return items;
  }
  function openDrawer(market, focus) {
    state.drawerMarket = market; state.lastFocus = focus || document.activeElement;
    $("drawer-title").textContent = `${marketName(market)} / ${loanName(market)}`;
    $("drawer-severity").replaceChildren(severityBadge(market.severity));
    $("drawer-block").textContent = `Block ${grouped(market.block_number ?? reportBlock() ?? "—")}`;
    $("drawer-id").textContent = market.market_id || "Market ID unavailable";
    const metrics = metricValues(market), metricsRoot = $("drawer-metrics"); metricsRoot.replaceChildren();
    const overviewMetrics = [
      ["Stored supply claims", usdc(metrics.stored_supply_assets_raw), "USDC, stored at last accrual"],
      ["Available liquidity", usdc(metrics.available_liquidity_raw, 6), "USDC, unborrowed at this block"],
      ["Share rate vs. initial", ratio(metrics.share_price_multiple_vs_initial), "Not a principal estimate"],
      ["Stored utilization", percentage(metrics.utilization), "Borrow assets / supply assets"]
    ];
    if (market.rate?.status === "ok") overviewMetrics.push(
      ["Supply accrual-rate indication", percentage(market.rate.supply_apr), "Annualized IRM indication; not a yield forecast"],
      ["Borrow accrual-rate indication", percentage(market.rate.borrow_apr), market.rate.rate_semantics || "Annualized IRM indication on stored state"]
    );
    for (const [label, value, note] of overviewMetrics) {
      const item = node("div", "drawer-metric"); item.append(node("span", null, label), node("strong", null, value), node("small", null, note)); metricsRoot.append(item);
    }
    const findings = market.findings || [], detectorRoot = $("detector-list");
    detectorRoot.replaceChildren(
      detectorCard("Oracle credibility", findings.filter((f) => detectorType(f) === "oracle"), "No completed oracle/reference-price check is included. A constant or repeated price alone does not establish credibility."),
      detectorCard("Accounting & liquidity", findings.filter((f) => detectorType(f) === "accounting"), "Accounting evidence is missing. Supply claims and free liquidity must be read at the same block."),
      detectorCard("Collateral exit depth", findings.filter((f) => detectorType(f) === "depth"), "No completed sale-depth check is included. Liquidation capacity has not been established.")
    );
    const other = findings.filter((f) => ["pending", "other"].includes(detectorType(f)));
    if (other.length) detectorRoot.append(detectorCard("Coverage & other findings", other, ""));
    const evidence = evidenceOf(market);
    $("raw-evidence").textContent = evidence.length ? JSON.stringify(evidence, null, 2) : "No raw call evidence was supplied for this market.";
    $("copy-evidence").disabled = !evidence.length;
    const drawer = $("market-drawer"); if (!drawer.open) drawer.showModal();
  }
  function closeDrawer() { $("market-drawer").close(); state.lastFocus?.focus?.(); }
  function setDestination(id) { state.selected = id; $("allocation-market").value = id; resetPreview(); renderMarkets(); if (!state.scanning) $("scan-button").querySelector("span").textContent = id ? "Check market" : "Refresh evidence"; }
  function resetPreview() {
    state.previewToken += 1;
    $("preview-context").textContent = reportBlock() != null ? `Preview will use report block ${grouped(reportBlock())}. No transactions.` : "Replay at the report's block. No historical profit claim.";
    $("original-action").textContent = "Waiting for a preview";
    $("original-rationale").textContent = "Run the original policy for this destination and amount.";
    $("gated-action").textContent = "Evidence required";
    $("gated-rationale").textContent = "The gate's actual decision will appear here.";
    $("allocator-error").hidden = true; $("allocator-raw").hidden = true;
    document.querySelector(".gated-step").classList.remove("is-blocked");
  }
  function actionParts(payload, keys) {
    for (const key of keys) if (payload?.[key]) {
      const value = payload[key];
      if (typeof value === "object") return value.action && typeof value.action === "object" ? { ...value, ...value.action } : value;
      if (typeof value === "string") return { kind: value };
    }
    return null;
  }
  function actionLabel(action) {
    const kind = action?.kind || action?.action;
    if (kind === "switch") return "Allocate to destination";
    if (kind === "hold") return "Keep capital unallocated";
    if (kind) return String(kind);
    return "No decision returned";
  }
  function actionExplanation(action, payload, gated) {
    if (gated && action?.kind === "hold" && payload.original?.kind === "switch") {
      const reasons = payload.admission?.findings?.filter((f) => ["block", "insufficient"].includes(f.severity));
      if (reasons?.length) return reasons.map((f) => /[.!?]$/.test(f.summary) ? f.summary : `${f.summary}.`).join(" ");
    }
    if (gated && action?.kind === "switch") return "The available evidence permits this proposal for the checked amount.";
    if (!gated && action?.kind === "switch") {
      const rate = payload.candidates?.find((c) => c.market_id === payload.market_id)?.supply_apr;
      if (rate !== null && rate !== undefined) return `The original policy proposes this market at a ${percentage(rate)} annualized accrual-rate indication. This is not a yield forecast.`;
    }
    return action?.rationale || action?.reason || "No rationale supplied by the policy.";
  }
  async function evaluate() {
    const amount = $("allocation-amount").value.trim().replaceAll(",", "");
    if (!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(amount) || !/[1-9]/.test(amount)) {
      $("allocator-error").textContent = "Enter a positive USDC amount with at most six decimal places."; $("allocator-error").hidden = false; return;
    }
    if (!validId(state.selected)) return;
    const token = ++state.previewToken;
    $("evaluate-button").disabled = true; $("allocator-error").hidden = true;
    $("original-action").textContent = "Evaluating…"; $("gated-action").textContent = "Checking admission…";
    try {
      const payload = await api(`/api/allocator?${new URLSearchParams({ amount, market: state.selected })}`);
      if (token !== state.previewToken) return;
      const original = actionParts(payload, ["original", "original_action", "baseline", "before"]);
      const gated = actionParts(payload, ["gated", "gated_action", "mirage", "after"]);
      $("preview-context").textContent = payload.block_number !== undefined ? `First allocation at block ${grouped(payload.block_number)}. No transactions.` : "First-allocation replay. No transactions.";
      $("original-action").textContent = actionLabel(original);
      $("original-rationale").textContent = actionExplanation(original, payload, false);
      $("gated-action").textContent = actionLabel(gated);
      $("gated-rationale").textContent = actionExplanation(gated, payload, true);
      document.querySelector(".gated-step").classList.toggle("is-blocked", gated?.kind === "hold" && original?.kind === "switch");
      $("allocator-json").textContent = JSON.stringify(payload, null, 2); $("allocator-raw").hidden = false;
      if (!original || !gated) { $("allocator-error").textContent = "The response did not contain both decisions. Inspect the response details."; $("allocator-error").hidden = false; }
      else if (payload.scenario_matches === false) { $("allocator-error").textContent = "Exit depth has not been checked for this amount. Use Check market to collect matching evidence."; $("allocator-error").hidden = false; }
    } catch (error) {
      if (token !== state.previewToken) return;
      $("original-action").textContent = "Preview unavailable"; $("gated-action").textContent = "No decision established";
      $("original-rationale").textContent = "The allocator did not return a usable preview."; $("gated-rationale").textContent = "Retry after resolving the request error.";
      $("allocator-error").textContent = error.message; $("allocator-error").hidden = false;
    } finally { $("evaluate-button").disabled = !state.selected; }
  }

  function statusState(status) {
    const value = String(status?.state || status?.status || "").toLowerCase();
    if (status?.running === true || status?.busy === true || ["running", "scanning", "queued", "in_progress"].includes(value)) return "running";
    if (["error", "failed"].includes(value) || status?.error) return "error";
    return "idle";
  }
  function renderStatus(status) {
    state.status = status;
    const kind = statusState(status), running = kind === "running";
    state.scanning = running;
    $("scan-button").disabled = running;
    $("new-market-submit").disabled = running;
    $("load-demo-button").disabled = running;
    $("scan-button").querySelector("span").textContent = running ? "Checking evidence" : state.selected ? "Check market" : "Refresh evidence";
    document.querySelector(".scan-panel").classList.toggle("is-scanning", running);
    const message = typeof status?.message === "string" ? status.message : typeof status?.error === "string" ? status.error : running ? "Reading Graph discovery and contract evidence…" : "No scan running";
    $("scan-status").textContent = message;
    const progress = status?.progress;
    const done = Number(progress?.done ?? progress?.completed ?? status?.completed), total = Number(progress?.total ?? status?.total);
    $("scan-progress").hidden = !running;
    if (running && Number.isFinite(done) && Number.isFinite(total) && total > 0) { $("scan-progress").max = total; $("scan-progress").value = done; }
    else $("scan-progress").removeAttribute("value");
    if (kind === "error") showNotice(message);
    renderProvenance();
  }
  async function loadReport() {
    const payload = await api("/api/report"), report = payload?.report || payload;
    if (!report || !Array.isArray(report.markets)) throw new Error("No market report is available. Run a scan or load saved evidence on the server.");
    state.report = report;
    state.markets = report.markets.filter((market) => market && validId(market.market_id)).map((market) => ({ ...market, findings: Array.isArray(market.findings) ? market.findings.filter((finding) => finding && typeof finding === "object") : [], severity: safeSeverity(market.severity) }));
    state.markets.sort((a, b) => ORDER[b.severity] - ORDER[a.severity] || marketName(a).localeCompare(marketName(b)));
    renderReport();
  }
  async function pollStatus() {
    clearTimeout(state.poll);
    try {
      const wasRunning = state.scanning;
      const status = await api("/api/status"); renderStatus(status);
      if (state.scanning) state.poll = setTimeout(pollStatus, 2000);
      else if (wasRunning) { await loadReport(); if (statusState(status) !== "error") hideNotice(); resetPreview(); }
    } catch (error) {
      state.scanning = false; renderStatus({ state: "error", message: error.message });
      showNotice(error.message, true);
    }
  }
  async function scan(explicitMarketId) {
    if (state.scanning) return false;
    const amount = $("allocation-amount").value.trim().replaceAll(",", "");
    if (!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(amount) || !/[1-9]/.test(amount)) {
      showNotice("Enter a positive USDC amount with at most six decimal places before checking the market."); return false;
    }
    hideNotice(); renderStatus({ state: "running", message: "Requesting live Graph discovery…" });
    try {
      const requestedId = explicitMarketId === undefined ? state.selected : explicitMarketId;
      const result = await api("/api/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount_usdc: amount, market_id: validId(requestedId) ? requestedId.toLowerCase() : null }) });
      if (result?.report || Array.isArray(result?.markets)) { await loadReport(); renderStatus({ state: "complete", message: "Report updated from the completed scan." }); resetPreview(); }
      else { if (result?.message) $("scan-status").textContent = result.message; state.poll = setTimeout(pollStatus, 500); }
      return true;
    } catch (error) { renderStatus({ state: "error", message: error.message }); showNotice(error.message, true); return false; }
  }
  async function initialize() {
    hideNotice();
    // Read status first: a completed capture must precede the report read.
    // If it was still running, polling will pick up its eventual report.
    const statusResult = (await Promise.allSettled([api("/api/status")]))[0];
    const reportResult = (await Promise.allSettled([loadReport()]))[0];
    const results = [reportResult, statusResult];
    if (results[0].status === "rejected") {
      const message = results[0].reason?.message || "Evidence could not be loaded.";
      showNotice(message, true); $("source-label").textContent = "Evidence unavailable";
      $("source-description").textContent = "Check that the MIRAGE local server is running, then retry.";
      $("empty-title").textContent = "No evidence loaded"; $("empty-description").textContent = "Connect to the local MIRAGE server to inspect a saved report or run a scan.";
    }
    if (results[1].status === "fulfilled") { renderStatus(results[1].value); if (state.scanning) state.poll = setTimeout(pollStatus, 2000); }
    else $("scan-status").textContent = "Scan status unavailable. The report may still be inspected.";
  }

  $("market-search").addEventListener("input", renderMarkets);
  $("risk-filter").addEventListener("change", renderMarkets);
  $("allocation-market").addEventListener("change", (event) => setDestination(event.target.value));
  $("allocation-amount").addEventListener("input", resetPreview);
  $("allocation-amount").addEventListener("keydown", (event) => { if (event.key === "Enter") evaluate(); });
  $("evaluate-button").addEventListener("click", evaluate);
  $("scan-button").addEventListener("click", () => scan());
  $("load-demo-button").addEventListener("click", async () => {
    if (state.scanning) return;
    try {
      renderStatus(await api("/api/demo", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}));
      await loadReport(); resetPreview(); hideNotice();
    } catch (error) { showNotice(error.message); }
  });
  $("add-market-toggle").addEventListener("click", () => {
    const open = $("add-market-form").hidden;
    $("add-market-form").hidden = !open;
    $("add-market-toggle").setAttribute("aria-expanded", String(open));
    if (open) $("new-market-id").focus();
  });
  $("new-market-id").addEventListener("input", () => { $("new-market-message").hidden = true; $("new-market-id").removeAttribute("aria-invalid"); });
  $("add-market-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("new-market-id").value.trim();
    if (!validId(id)) {
      $("new-market-message").textContent = "Enter a complete 32-byte market ID: 0x followed by 64 hexadecimal characters.";
      $("new-market-message").hidden = false; $("new-market-id").setAttribute("aria-invalid", "true"); return;
    }
    // A request is not evidence: no row or destination is created here.
    const accepted = await scan(id);
    if (accepted) { $("new-market-message").textContent = "Check requested. The existing report stays visible until the new evidence is complete."; $("new-market-message").hidden = false; }
  });
  $("retry-button").addEventListener("click", initialize);
  $("method-button").addEventListener("click", () => $("method").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));
  $("copy-block").addEventListener("click", () => state.report?.block_hash && copy(state.report.block_hash));
  $("close-drawer").addEventListener("click", closeDrawer);
  $("market-drawer").addEventListener("click", (event) => { if (event.target === $("market-drawer") && event.clientX < $("market-drawer").getBoundingClientRect().left) closeDrawer(); });
  $("market-drawer").addEventListener("close", () => state.lastFocus?.focus?.());
  $("copy-evidence").addEventListener("click", () => state.drawerMarket && copy(JSON.stringify(evidenceOf(state.drawerMarket), null, 2)));
  $("use-market").addEventListener("click", () => { if (!state.drawerMarket) return; setDestination(state.drawerMarket.market_id); closeDrawer(); $("allocation-amount").focus(); document.querySelector(".allocator-panel").scrollIntoView({ behavior: "smooth", block: "nearest" }); });
  window.addEventListener("beforeunload", () => clearTimeout(state.poll));
  initialize();
})();
