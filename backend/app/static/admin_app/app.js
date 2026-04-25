(function () {
  const API_BASE = `${window.location.origin}/api/v1`;
  const TOKEN_KEY = "hph_admin_token";
  const PALETTE = {
    blue: "#27235f",
    white: "#fff",
    orange: "#f47227",
  };
  const $ = (id) => document.getElementById(id);

  const state = {
    token: "",
    currentUser: null,
    selectedDeviceCode: "",
    selectedKioskTab: "experience",
    knownDevices: [],
    customerExperience: null,
    chartHistory: { uptime: [], errors: [], alerts: [] },
    livePulseHandle: null,
    refreshAllInFlight: false,
    qrObjectUrls: { customer: null, wifi: null },
  };

  const ids = [
    "authScreen", "appShell", "authStatus", "loginForm", "loginEmail", "loginPassword", "showForgotBtn", "showResetBtn",
    "forgotForm", "forgotEmail", "resetForm", "resetToken", "resetPassword", "status", "currentUserLabel", "logoutBtn",
    "refreshAllBtn", "globalDeviceSelector", "globalDeviceReloadBtn", "kpiConfirmedPayments", "kpiConfirmedAmount", "kpiPrintedJobs",
    "kpiActiveDevices", "kpiAvgUptimeHours", "kpiErrorEvents24h", "overviewRecentPaymentsBody", "overviewDeviceMonitor", "uptimeChart",
    "errorChart", "alertChart", "devicesIncludeInactive", "devicesBody", "paymentsFilters", "paymentsReloadBtn", "paymentsStatus",
    "paymentsMethod", "paymentsLifecycle", "paymentsProvider", "paymentsLimit", "paymentsBody", "reportsReloadBtn", "reportPaymentsTotal",
    "reportPaymentsConfirmed", "reportPaymentsPending", "reportPaymentsFailed", "reportJobsPrinted", "reportJobsProgress", "reportDevicesActive",
    "reportDevicesOnline", "reportHistoryReloadBtn", "reportHistoryFilters", "reportHistoryDays", "reportCleanupDays", "reportCleanupDryRunBtn",
    "reportCleanupRunBtn", "reportHistoryBody", "reportRetentionPreview", "pricingForm", "pricingReloadBtn", "pricingA4Bw", "pricingA4Color",
    "pricingA3Bw", "pricingA3Color", "pricingCurrency", "pricingColorProfile", "pricingPaperProfile", "pricingPreview", "pricingCapabilityPreview",
    "customerExperienceForm", "customerExperienceReloadBtn", "customerAvailabilityReloadBtn", "customerAvailabilityPreview", "cxActiveDeviceCode",
    "cxSiteStripText", "cxBrandTitle", "cxBrandNote", "cxWelcomeTitle", "cxWelcomeLead", "cxSupportPhone", "cxChip1", "cxChip2", "cxChip3",
    "cxBrandBlue", "cxBrandOrange", "cxHidePaymentMethod", "cxShowStepper", "cxDefaultPaymentMethod", "cxUploadsEnabled", "cxPaymentsEnabled",
    "cxPauseReason", "cxPrinterUnreadyMessage", "cxHotspotEnabled", "cxHotspotSsid", "cxHotspotPassphrase", "cxHotspotSecurity", "cxHotspotCountry",
    "cxHotspotChannel", "deviceActionForm", "deviceActionDeviceCode", "deviceActionSudoPassword", "deviceActionNote", "actionPauseKioskBtn",
    "actionResumeKioskBtn", "actionApplyHotspotBtn", "actionDisableHotspotBtn", "actionRestartAgentBtn", "actionRestartApiBtn", "actionRebootDeviceBtn",
    "qrPackReloadBtn", "qrEntryUrl", "qrLanEntryUrl", "wifiQrPayload", "qrPreview", "wifiQrPreview", "qrHint", "qrCopyBtn", "qrLanCopyBtn", "wifiCopyBtn", "qrOpenBtn",
    "refundsReloadBtn", "refundCreateForm", "refundPaymentId", "refundReason", "refundRequestedBy", "refundFilters", "refundStatusFilter",
    "refundPaymentFilter", "refundActorName", "refundDecisionNote", "refundsBody", "usersReloadBtn", "userCreateForm", "userCreateName",
    "userCreateEmail", "userCreateRole", "userCreatePassword", "usersBody"
  ];
  const ui = Object.fromEntries(ids.map((id) => [id, $(id)]));
  ui.tabs = document.querySelectorAll(".tab");
  ui.views = document.querySelectorAll("[data-view-panel]");
  ui.kioskSubtabs = document.querySelectorAll(".subtab");
  ui.kioskPanels = document.querySelectorAll("[data-kiosk-panel]");

  const setTone = (el, tone) => {
    el.style.color = tone === "bad" ? PALETTE.orange : PALETTE.white;
  };
  const setAuthStatus = (message, tone = "") => { ui.authStatus.textContent = message || ""; setTone(ui.authStatus, tone); };
  const setStatus = (message, tone = "") => { ui.status.textContent = message || ""; setTone(ui.status, tone); };

  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  const money = (v, c) => `${Number(v || 0).toFixed(0)} ${String(c || "TZS").toUpperCase()}`;
  const boolVal = (v) => String(v || "").toLowerCase() === "true";
  const fmt = (v) => { const d = new Date(v); return v && !Number.isNaN(d.getTime()) ? d.toLocaleString() : "-"; };
  const q = (o) => { const s = new URLSearchParams(); Object.entries(o || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") s.set(k, String(v)); }); return s.toString(); };
  const canManageAdmins = () => ["super_admin", "admin"].includes(String(state.currentUser?.role || "").toLowerCase());
  const canManagePricingAndRefunds = () => canManageAdmins();

  async function api(path, options = {}, auth = true) {
    const headers = { ...(options.headers || {}) };
    if (auth) {
      if (!state.token) throw new Error("Signed out.");
      headers.Authorization = `Bearer ${state.token}`;
    }
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    let payload = null;
    try { payload = await res.json(); } catch (_e) { payload = null; }
    if (!res.ok) {
      if (res.status === 401 && auth) logout(false);
      throw new Error(payload?.detail ? (typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail)) : `HTTP ${res.status}`);
    }
    return payload;
  }

  function showAuth(mode = "") {
    stopLivePulse();
    ui.authScreen.classList.remove("hidden");
    ui.appShell.classList.add("hidden");
    ui.forgotForm.classList.toggle("hidden", mode !== "forgot");
    ui.resetForm.classList.toggle("hidden", mode !== "reset");
  }

  function showApp() {
    ui.authScreen.classList.add("hidden");
    ui.appShell.classList.remove("hidden");
  }

  async function login(email, password) {
    const payload = await api("/admin/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }, false);
    state.token = payload.access_token;
      state.currentUser = payload.user;
      localStorage.setItem(TOKEN_KEY, state.token);
      ui.currentUserLabel.textContent = `${payload.user.full_name} (${payload.user.role})`;
      setRoleVisibility();
  }

  async function restoreSession() {
    state.token = localStorage.getItem(TOKEN_KEY) || "";
    if (!state.token) return false;
    try {
      state.currentUser = await api("/admin/auth/me", { method: "GET" });
      ui.currentUserLabel.textContent = `${state.currentUser.full_name} (${state.currentUser.role})`;
      setRoleVisibility();
      return true;
    } catch (_e) {
      logout(false);
      return false;
    }
  }

  function logout(showMsg = true) {
    stopLivePulse();
    if (state.qrObjectUrls.customer) URL.revokeObjectURL(state.qrObjectUrls.customer);
    if (state.qrObjectUrls.wifi) URL.revokeObjectURL(state.qrObjectUrls.wifi);
    state.qrObjectUrls = { customer: null, wifi: null };
    state.token = "";
    state.currentUser = null;
    localStorage.removeItem(TOKEN_KEY);
    setRoleVisibility();
    showAuth();
    if (showMsg) setStatus("Signed out.", "ok");
  }

  function showView(view) {
    ui.tabs.forEach((t) => t.classList.toggle("active", t.dataset.view === view));
    ui.views.forEach((p) => p.classList.toggle("active", p.dataset.viewPanel === view));
    if (view === "kiosk") showKiosk(state.selectedKioskTab || "experience");
  }

  function showKiosk(tab) {
    state.selectedKioskTab = tab;
    ui.kioskSubtabs.forEach((t) => t.classList.toggle("active", t.dataset.kioskTab === tab));
    ui.kioskPanels.forEach((p) => p.classList.toggle("active", p.dataset.kioskPanel === tab));
  }

  function setRows(tbody, html) {
    tbody.innerHTML = html || '<tr><td colspan="20">No data</td></tr>';
  }

  function chip(raw) {
    const value = String(raw || "").toLowerCase();
    const tone = value.includes("ok") || value.includes("online") || value.includes("ready") || value.includes("confirmed") || value.includes("printed") ? "ok"
      : (value.includes("pending") || value.includes("warning") || value.includes("unknown") || value.includes("degraded")
        ? "warn"
        : (value.includes("failed") || value.includes("offline") || value.includes("critical") || value.includes("disconnected") ? "bad" : ""));
    return `<span class="chip ${tone}">${esc(raw || "-")}</span>`;
  }

  function currentScope() { return String(state.selectedDeviceCode || "").trim(); }
  function currentDevice() { return String(ui.deviceActionDeviceCode.value || ui.cxActiveDeviceCode.value || currentScope() || "pi-kiosk-001").trim(); }

  function setRoleVisibility() {
    const usersTab = Array.from(ui.tabs).find((tab) => tab.dataset.view === "users");
    const pricingTab = Array.from(ui.tabs).find((tab) => tab.dataset.view === "pricing");
    const refundsTab = Array.from(ui.tabs).find((tab) => tab.dataset.view === "refunds");
    const canManage = canManageAdmins();
    const canFinance = canManagePricingAndRefunds();

    if (usersTab) usersTab.classList.toggle("hidden", !canManage);
    if (pricingTab) pricingTab.classList.toggle("hidden", !canFinance);
    if (refundsTab) refundsTab.classList.toggle("hidden", !canFinance);

    if (!canManage && usersTab?.classList.contains("active")) {
      showView("overview");
    }
    if (!canFinance && (pricingTab?.classList.contains("active") || refundsTab?.classList.contains("active"))) {
      showView("overview");
    }

    if (ui.userCreateRole) {
      const superRoleOption = Array.from(ui.userCreateRole.options).find((opt) => opt.value === "super_admin");
      if (superRoleOption) {
        superRoleOption.disabled = state.currentUser?.role !== "super_admin";
        superRoleOption.hidden = state.currentUser?.role !== "super_admin";
        if (state.currentUser?.role !== "super_admin" && ui.userCreateRole.value === "super_admin") {
          ui.userCreateRole.value = "admin";
        }
      }
    }
  }

  function paymentRows(items) {
    return (items || []).map((item) => `
      <tr>
        <td>${esc(fmt(item.requested_at))}</td>
        <td>${esc(item.provider_request_id || "-")}</td>
        <td>${chip(item.method)}</td>
        <td>${chip(item.status)}</td>
        <td>${chip(item.lifecycle || "other")}</td>
        <td>${esc(money(item.amount, item.currency))}</td>
        <td>${esc([item.customer_name, item.customer_msisdn].filter(Boolean).join(" | ") || "-")}</td>
        <td>${esc(item.document_name || "-")}</td>
        <td>${esc(item.print_job_id || "-")}</td>
        <td>${esc(item.device_code || "-")}</td>
      </tr>
    `).join("");
  }

  function pushTrend(name, value) {
    state.chartHistory[name].push(Number(value || 0));
    if (state.chartHistory[name].length > 36) state.chartHistory[name].shift();
  }

  function drawTrend(svg, arr, color) {
    if (!svg) return;
    if (!arr.length) { svg.innerHTML = ""; return; }
    const max = Math.max(1, ...arr);
    const w = 340;
    const h = 90;
    const step = arr.length > 1 ? w / (arr.length - 1) : w;
    const points = arr.map((v, i) => `${(i * step).toFixed(2)},${(h - ((v / max) * (h - 10)) - 4).toFixed(2)}`).join(" ");
    const end = points.split(" ").slice(-1)[0] || "0,0";
    const [cx, cy] = end.split(",");
    const area = `${points} ${w},${h} 0,${h}`;
    const gridLines = [16, 32, 48, 64, 80]
      .map((y) => `<line x1="0" y1="${y}" x2="${w}" y2="${y}" stroke="rgba(255, 255, 255, 0.18)" stroke-width="1"></line>`)
      .join("");
    svg.innerHTML = `
      ${gridLines}
      <polygon points="${area}" fill="${color}" opacity="0.12"></polygon>
      <polyline fill="none" stroke="${color}" stroke-width="2.2" points="${points}"></polyline>
      <circle cx="${cx}" cy="${cy}" r="3.3" fill="${color}">
        <animate attributeName="r" values="2.8;4.8;2.8" dur="1s" repeatCount="indefinite"></animate>
        <animate attributeName="opacity" values="0.8;1;0.8" dur="1s" repeatCount="indefinite"></animate>
      </circle>
    `;
  }

  function stopLivePulse() {
    if (state.livePulseHandle) {
      window.clearInterval(state.livePulseHandle);
      state.livePulseHandle = null;
    }
  }

  function startLivePulse() {
    stopLivePulse();
    state.livePulseHandle = window.setInterval(async () => {
      if (!state.token || document.hidden) return;
      try {
        await loadOverview();
      } catch (_err) {
        // Ignore pulse errors; manual refresh will report user-visible issues.
      }
    }, 8000);
  }

  async function loadDevicesOptions() {
    const payload = await api("/admin/devices?include_inactive=true", { method: "GET" });
    state.knownDevices = (payload.items || []).map((x) => ({ device_code: x.device_code, site_name: x.site_name || "" })).sort((a, b) => a.device_code.localeCompare(b.device_code));
    const prev = currentScope();
    ui.globalDeviceSelector.innerHTML = ['<option value="">All devices</option>', ...state.knownDevices.map((x) => `<option value="${esc(x.device_code)}">${esc(`${x.device_code}${x.site_name ? ` (${x.site_name})` : ""}`)}</option>`)].join("");
    if (prev && state.knownDevices.some((x) => x.device_code === prev)) ui.globalDeviceSelector.value = prev;
  }

  async function loadOverview() {
    const payload = await api(`/admin/dashboard/snapshot?${q({ recent_payments_limit: 200, pending_incidents_limit: 1, device_code: currentScope() })}`, { method: "GET" });
    const k = payload.kpis || {};
    const m = payload.monitor || {};
    const s = m.summary || {};
    ui.kpiConfirmedPayments.textContent = String(k.confirmed_payments_today ?? 0);
    ui.kpiConfirmedAmount.textContent = money(k.confirmed_amount_today, payload.pricing?.currency || "TZS");
    ui.kpiPrintedJobs.textContent = String(k.printed_jobs_today ?? 0);
    ui.kpiActiveDevices.textContent = String(k.active_devices ?? 0);
    ui.kpiAvgUptimeHours.textContent = String(s.avg_uptime_hours ?? 0);
    ui.kpiErrorEvents24h.textContent = String(s.total_error_events_24h ?? 0);
    setRows(ui.overviewRecentPaymentsBody, paymentRows(payload.recent_payments?.items || []));

    const devices = m.devices || [];
    ui.overviewDeviceMonitor.innerHTML = devices.length
      ? devices.map((d) => `<article class="monitor-card"><div class="monitor-title"><span>${esc(d.device_code || "-")}</span><span>${chip(d.status || "-")}</span></div><p class="monitor-meta">Printer: ${chip(d.printer_status || "-")} ${esc(d.printer_name ? `(${d.printer_name})` : "")}</p><p class="monitor-meta">Uptime: ${esc(d.uptime_hours)} hrs</p><p class="monitor-meta">Errors(24h): ${esc(d.error_events_24h)}</p><p class="monitor-meta">Active Alerts: ${esc(d.active_alerts)}</p><p class="monitor-meta">Paper/Toner/Ink: ${esc(d.paper_level_pct ?? "-")}% / ${esc(d.toner_level_pct ?? "-")}% / ${esc(d.ink_level_pct ?? "-")}%</p><p class="monitor-meta">Last Error: ${esc(d.active_error || d.printer_details || "-")}</p><p class="monitor-meta">Last Seen: ${esc(fmt(d.last_seen_at))}</p></article>`).join("")
      : '<p class="hint">No device telemetry available yet.</p>';

    pushTrend("uptime", s.avg_uptime_hours || 0);
    pushTrend("errors", s.total_error_events_24h || 0);
    pushTrend("alerts", s.total_active_alerts || 0);
    drawTrend(ui.uptimeChart, state.chartHistory.uptime, PALETTE.blue);
    drawTrend(ui.errorChart, state.chartHistory.errors, PALETTE.orange);
    drawTrend(ui.alertChart, state.chartHistory.alerts, PALETTE.white);
  }

  async function loadDevices() {
    const payload = await api(`/admin/devices?include_inactive=${ui.devicesIncludeInactive.checked ? "true" : "false"}`, { method: "GET" });
    const rows = (payload.items || []).map((d) => `
      <tr>
        <td>${esc(d.device_code)}</td>
        <td>${esc(d.site_name || "-")}</td>
        <td>${chip(d.status)}</td>
        <td>${chip(d.printer_status)} ${esc(d.printer_name ? `(${d.printer_name})` : "")}</td>
        <td>${esc([d.printer_capabilities?.color_enabled ? "Color + B/W" : "B/W only", d.printer_capabilities?.a3_enabled ? "A3 + A4" : "A4 only"].join(" | "))}</td>
        <td>${esc(fmt(d.last_seen_at))}</td>
        <td>${esc(d.active_alerts)}</td>
        <td>${esc(`T:${d.jobs.total} P:${d.jobs.printed} F:${d.jobs.failed}`)}</td>
      </tr>
    `).join("");
    setRows(ui.devicesBody, rows);
  }

  async function loadPayments() {
    const payload = await api(`/admin/payments?${q({ limit: ui.paymentsLimit.value || 100, status: ui.paymentsStatus.value, method: ui.paymentsMethod.value, lifecycle: ui.paymentsLifecycle.value, provider: ui.paymentsProvider.value.trim(), device_code: currentScope() })}`, { method: "GET" });
    setRows(ui.paymentsBody, paymentRows(payload.items || []));
  }

  async function loadReport() {
    const p = await api(`/admin/reports/today?${q({ device_code: currentScope() })}`, { method: "GET" });
    ui.reportPaymentsTotal.textContent = String(p.payments?.total ?? 0);
    ui.reportPaymentsConfirmed.textContent = String(p.payments?.confirmed ?? 0);
    ui.reportPaymentsPending.textContent = String(p.payments?.pending ?? 0);
    ui.reportPaymentsFailed.textContent = String(p.payments?.failed ?? 0);
    ui.reportJobsPrinted.textContent = String(p.jobs?.printed ?? 0);
    ui.reportJobsProgress.textContent = String(p.jobs?.in_progress ?? 0);
    ui.reportDevicesActive.textContent = String(p.devices?.active ?? 0);
    ui.reportDevicesOnline.textContent = String(p.devices?.online ?? 0);
  }

  async function loadReportHistory() {
    const p = await api(`/admin/reports/history?${q({ days: Number(ui.reportHistoryDays.value || 90), device_code: currentScope() })}`, { method: "GET" });
    setRows(ui.reportHistoryBody, (p.daily || []).map((d) => `<tr><td>${esc(d.date)}</td><td>${esc(`${d.payments_confirmed || 0}/${d.payments_total || 0}`)}</td><td>${esc(money(d.confirmed_amount || 0, ui.pricingCurrency.value || "TZS"))}</td><td>${esc(`${d.jobs_printed || 0}/${d.jobs_total || 0}`)}</td><td>${esc(d.jobs_failed || 0)}</td><td>${esc(`${d.alerts_critical || 0}/${d.alerts_total || 0}`)}</td></tr>`).join(""));
    const r = p.retention || {};
    const c = r.cleanup_candidates || {};
    ui.reportRetentionPreview.textContent = [`Retention: ${r.days || 90} days`, `Cutoff: ${fmt(r.cutoff_utc)}`, `Old logs: ${c.logs ?? 0}`, `Old resolved alerts: ${c.resolved_alerts ?? 0}`, `Old print jobs: ${c.print_jobs ?? 0}`, `Old payments: ${c.payments ?? 0}`].join(" | ");
  }

  async function runCleanup(dry) {
    const p = await api(`/admin/reports/cleanup?${q({ retention_days: Number(ui.reportCleanupDays.value || 90), dry_run: dry ? "true" : "false", device_code: currentScope() })}`, { method: "POST" });
    if (p.status === "dry_run") setStatus(`Dry run: logs=${p.delete_candidates?.logs || 0}, resolved_alerts=${p.delete_candidates?.resolved_alerts || 0}`, "ok");
    else setStatus(`Cleanup complete: logs=${p.deleted?.logs || 0}, resolved_alerts=${p.deleted?.resolved_alerts || 0}`, "ok");
  }

  function resolveCaps(config, deviceCode) {
    const pc = config?.printer_capabilities || {};
    const defaults = pc.default || {};
    const base = { color_enabled: Boolean(defaults.color_enabled !== false), a3_enabled: Boolean(defaults.a3_enabled) };
    const per = pc.devices?.[String(deviceCode || "").trim()];
    if (!per || typeof per !== "object") return base;
    return { color_enabled: Boolean(per.color_enabled !== false), a3_enabled: Boolean(per.a3_enabled) };
  }

  function setProfilesFromCaps(c) {
    ui.pricingColorProfile.value = c?.color_enabled ? "bw_color" : "bw_only";
    ui.pricingPaperProfile.value = c?.a3_enabled ? "a4_a3" : "a4_only";
  }

  function capsFromProfiles() {
    return { color_enabled: ui.pricingColorProfile.value !== "bw_only", a3_enabled: ui.pricingPaperProfile.value === "a4_a3" };
  }

  function syncHotspotSecurityUi() {
    const nopass = String(ui.cxHotspotSecurity.value || "").toUpperCase() === "NOPASS";
    ui.cxHotspotPassphrase.disabled = nopass;
    ui.cxHotspotPassphrase.placeholder = nopass ? "Not required for open hotspot" : "Hotspot password";
    if (nopass) ui.cxHotspotPassphrase.value = "";
  }

  function updatePricingPreview() {
    const currency = String(ui.pricingCurrency.value || "TZS").toUpperCase();
    ui.pricingPreview.textContent = [`A4 BW: ${Number(ui.pricingA4Bw.value || 0).toFixed(0)} ${currency}`, `A4 Color: ${Number(ui.pricingA4Color.value || 0).toFixed(0)} ${currency}`, `A3 BW: ${Number(ui.pricingA3Bw.value || 0).toFixed(0)} ${currency}`, `A3 Color: ${Number(ui.pricingA3Color.value || 0).toFixed(0)} ${currency}`].join(" | ");
    const c = capsFromProfiles();
    ui.pricingCapabilityPreview.textContent = `Capabilities (${currentScope() || currentDevice()}): ${c.color_enabled ? "Color + B/W" : "B/W only"} | ${c.a3_enabled ? "A3 + A4" : "A4 only"}`;
  }

  function fillCX(config) {
    state.customerExperience = config || {};
    const c = config.content || {};
    const f = config.flow || {};
    const o = config.operations || {};
    const h = config.hotspot || {};
    const chips = Array.isArray(config.chips) ? config.chips : [];
    ui.cxActiveDeviceCode.value = config.active_device_code || "pi-kiosk-001";
    ui.cxSiteStripText.value = config.site_strip_text || "";
    ui.cxBrandTitle.value = c.brand_title || "";
    ui.cxBrandNote.value = c.brand_note || "";
    ui.cxWelcomeTitle.value = c.welcome_title || "";
    ui.cxWelcomeLead.value = c.welcome_lead || "";
    ui.cxSupportPhone.value = c.support_phone || "";
    ui.cxChip1.value = chips[0] || "";
    ui.cxChip2.value = chips[1] || "";
    ui.cxChip3.value = chips[2] || "";
    ui.cxBrandBlue.value = PALETTE.blue;
    ui.cxBrandOrange.value = PALETTE.orange;
    ui.cxBrandBlue.disabled = true;
    ui.cxBrandOrange.disabled = true;
    ui.cxHidePaymentMethod.value = String(f.hide_payment_method !== false);
    ui.cxShowStepper.value = String(f.show_stepper !== false);
    ui.cxDefaultPaymentMethod.value = f.default_payment_method || "mpesa";
    ui.cxUploadsEnabled.value = String(o.uploads_enabled !== false);
    ui.cxPaymentsEnabled.value = String(o.payments_enabled !== false);
    ui.cxPauseReason.value = o.pause_reason || "";
    ui.cxPrinterUnreadyMessage.value = o.printer_unready_message || "";
    ui.cxHotspotEnabled.value = String(Boolean(h.enabled));
    ui.cxHotspotSsid.value = h.ssid || "";
    ui.cxHotspotPassphrase.value = h.passphrase || "";
    ui.cxHotspotSecurity.value = h.wifi_security || "NOPASS";
    ui.cxHotspotCountry.value = h.country || "TZ";
    ui.cxHotspotChannel.value = String(Number(h.channel || 6));
    ui.deviceActionDeviceCode.value = currentDevice();
    syncHotspotSecurityUi();
  }

  function cxPayload() {
    const hotspotSecurity = String(ui.cxHotspotSecurity.value || "NOPASS").toUpperCase();
    const hotspotPassphrase = hotspotSecurity === "WPA" ? String(ui.cxHotspotPassphrase.value || "").trim() : "";
    return {
      active_device_code: String(ui.cxActiveDeviceCode.value || "").trim() || "pi-kiosk-001",
      site_strip_text: String(ui.cxSiteStripText.value || "").trim(),
      content: {
        brand_title: String(ui.cxBrandTitle.value || "").trim(),
        brand_note: String(ui.cxBrandNote.value || "").trim(),
        welcome_title: String(ui.cxWelcomeTitle.value || "").trim(),
        welcome_lead: String(ui.cxWelcomeLead.value || "").trim(),
        support_phone: String(ui.cxSupportPhone.value || "").trim(),
      },
      chips: [ui.cxChip1.value, ui.cxChip2.value, ui.cxChip3.value].map((x) => String(x || "").trim()).filter(Boolean),
      theme: { ...(state.customerExperience?.theme || {}), brand_blue: PALETTE.blue, brand_orange: PALETTE.orange },
      flow: { ...(state.customerExperience?.flow || {}), hide_payment_method: boolVal(ui.cxHidePaymentMethod.value), show_stepper: boolVal(ui.cxShowStepper.value), default_payment_method: String(ui.cxDefaultPaymentMethod.value || "mpesa").toLowerCase() },
      operations: { ...(state.customerExperience?.operations || {}), uploads_enabled: boolVal(ui.cxUploadsEnabled.value), payments_enabled: boolVal(ui.cxPaymentsEnabled.value), pause_reason: String(ui.cxPauseReason.value || "").trim(), printer_unready_message: String(ui.cxPrinterUnreadyMessage.value || "").trim() },
      hotspot: { ...(state.customerExperience?.hotspot || {}), enabled: boolVal(ui.cxHotspotEnabled.value), ssid: String(ui.cxHotspotSsid.value || "").trim(), passphrase: hotspotPassphrase, wifi_security: hotspotSecurity, country: String(ui.cxHotspotCountry.value || "TZ").toUpperCase(), channel: Number(ui.cxHotspotChannel.value || 6) },
    };
  }

  async function loadCX() { fillCX(await api("/admin/customer-experience", { method: "GET" })); }
  async function saveCX() { fillCX(await api("/admin/customer-experience", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload: cxPayload() }) })); }

  async function loadPricing() {
    const p = await api("/admin/pricing", { method: "GET" });
    ui.pricingA4Bw.value = p.a4_bw_price_per_page;
    ui.pricingA4Color.value = p.a4_color_price_per_page;
    ui.pricingA3Bw.value = p.a3_bw_price_per_page;
    ui.pricingA3Color.value = p.a3_color_price_per_page;
    ui.pricingCurrency.value = p.currency;
    if (!state.customerExperience) await loadCX();
    setProfilesFromCaps(resolveCaps(state.customerExperience || {}, currentScope() || currentDevice()));
    updatePricingPreview();
  }

  async function savePricing() {
    await api("/admin/pricing", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bw_price_per_page: Number(ui.pricingA4Bw.value || 0),
        color_price_per_page: Number(ui.pricingA4Color.value || 0),
        a4_bw_price_per_page: Number(ui.pricingA4Bw.value || 0),
        a4_color_price_per_page: Number(ui.pricingA4Color.value || 0),
        a3_bw_price_per_page: Number(ui.pricingA3Bw.value || 0),
        a3_color_price_per_page: Number(ui.pricingA3Color.value || 0),
        currency: String(ui.pricingCurrency.value || "TZS").trim().toUpperCase(),
      }),
    });
    if (!state.customerExperience) await loadCX();
    const updated = { ...(state.customerExperience || {}) };
    const pc = updated.printer_capabilities || {};
    const dev = { ...(pc.devices || {}) };
    dev[currentScope() || currentDevice()] = capsFromProfiles();
    updated.printer_capabilities = { default: { color_enabled: Boolean(pc.default?.color_enabled !== false), a3_enabled: Boolean(pc.default?.a3_enabled) }, devices: dev };
    fillCX(await api("/admin/customer-experience", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload: updated }) }));
  }

  async function loadAvailability() {
    const p = await api(`/admin/customer-availability?${q({ device_code: currentDevice() })}`, { method: "GET" });
    const a = p.availability || {};
    const c = p.printer_capabilities || {};
    ui.customerAvailabilityPreview.textContent = [`Device: ${p.device_code || "-"}`, `Upload: ${a.can_upload ? "enabled" : "blocked"}`, `Payment: ${a.can_pay ? "enabled" : "blocked"}`, `Color: ${c.color_enabled ? "enabled" : "disabled"}`, `A3: ${c.a3_enabled ? "enabled" : "disabled"}`, `Reason: ${a.reason_code || "-"}`, `Message: ${a.message || "-"}`].join(" | ");
  }

  async function setQr(kind, img, value) {
    const previous = state.qrObjectUrls[kind];
    if (previous) {
      URL.revokeObjectURL(previous);
      state.qrObjectUrls[kind] = null;
    }
    if (!value) {
      img.removeAttribute("src");
      return;
    }
    const res = await fetch(`${API_BASE}/admin/qr-code?${q({ data: value, box_size: 8 })}`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!res.ok) {
      throw new Error(`QR image load failed (HTTP ${res.status})`);
    }
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    state.qrObjectUrls[kind] = objectUrl;
    img.src = objectUrl;
  }
  async function loadQrPack() {
    const p = await api(`/admin/devices/${encodeURIComponent(currentDevice())}/qr-pack`, { method: "GET" });
    ui.qrEntryUrl.value = p.entry_url || "";
    ui.qrLanEntryUrl.value = p.lan_entry_url || "";
    ui.wifiQrPayload.value = p.wifi?.wifi_qr_payload || "";
    await setQr("customer", ui.qrPreview, ui.qrEntryUrl.value);
    await setQr("wifi", ui.wifiQrPreview, ui.wifiQrPayload.value);
    ui.qrHint.textContent = `${p.notes?.join(" ") || ""} Hotspot status: ${p.wifi?.active ? "active" : "inactive"}.`;
  }

  async function action(name) {
    return await api(`/admin/devices/${encodeURIComponent(currentDevice())}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: name, sudo_password: String(ui.deviceActionSudoPassword.value || ""), note: String(ui.deviceActionNote.value || ""), confirm_reboot: name === "reboot_device" }) });
  }

  async function loadRefunds() {
    const p = await api(`/admin/refunds?${q({ status: ui.refundStatusFilter.value.trim(), payment_id: ui.refundPaymentFilter.value.trim() })}`, { method: "GET" });
    setRows(ui.refundsBody, (p.items || []).map((r) => {
      let actions = "-";
      if (r.status === "requested") actions = `<div class="inline-actions"><button data-refund-action="approve" data-refund-id="${esc(r.refund_id)}" type="button">Approve</button><button data-refund-action="reject" data-refund-id="${esc(r.refund_id)}" type="button" class="danger">Reject</button></div>`;
      if (r.status === "approved") actions = `<div class="inline-actions"><button data-refund-action="execute" data-refund-id="${esc(r.refund_id)}" type="button">Execute</button><button data-refund-action="reject" data-refund-id="${esc(r.refund_id)}" type="button" class="danger">Reject</button></div>`;
      return `<tr><td>${esc(r.refund_id || "-")}</td><td>${esc(r.payment_id || "-")}</td><td>${chip(r.status || "-")}</td><td>${esc(r.reason || "-")}</td><td>${esc(r.requested_by || "-")}</td><td>${esc(fmt(r.updated_at || r.created_at))}</td><td>${actions}</td></tr>`;
    }).join(""));
  }

  async function loadUsers() {
    const p = await api("/admin/users", { method: "GET" });
    const isSuper = state.currentUser?.role === "super_admin";
    setRows(
      ui.usersBody,
      (p.items || []).map((u) => {
        const roleOptions = [
          `<option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>`,
          `<option value="technician" ${u.role === "technician" ? "selected" : ""}>technician</option>`,
          `<option value="monitor" ${u.role === "monitor" || u.role === "accountant" ? "selected" : ""}>monitor</option>`,
          `<option value="super_admin" ${u.role === "super_admin" ? "selected" : ""} ${isSuper ? "" : "disabled"}>super_admin</option>`,
        ].join("");
        return `<tr data-user-id="${esc(u.id)}"><td><input data-user-name type="text" value="${esc(u.full_name)}"></td><td>${esc(u.email)}</td><td><select data-user-role>${roleOptions}</select></td><td><select data-user-active><option value="true" ${u.is_active ? "selected" : ""}>active</option><option value="false" ${!u.is_active ? "selected" : ""}>disabled</option></select></td><td>${esc(fmt(u.last_login_at))}</td><td><div class="inline-actions"><input data-user-password type="password" placeholder="new password"><button data-user-save type="button">Save</button></div></td></tr>`;
      }).join(""),
    );
  }

  async function refreshAll() {
    if (state.refreshAllInFlight) return;
    state.refreshAllInFlight = true;
    setStatus("Refreshing admin panels...");
    try {
      await loadDevicesOptions();
      await Promise.all([loadCX(), loadOverview(), loadDevices(), loadPayments(), loadReport(), loadReportHistory(), loadPricing(), loadAvailability(), loadQrPack(), loadRefunds()]);
      if (canManageAdmins()) await loadUsers();
      setStatus("All admin panels refreshed.", "ok");
    } catch (err) {
      setStatus(`Refresh failed: ${err.message}`, "bad");
    } finally {
      state.refreshAllInFlight = false;
    }
  }

  function bindTabs() {
    ui.tabs.forEach((t) => t.addEventListener("click", () => showView(t.dataset.view)));
    ui.kioskSubtabs.forEach((t) => t.addEventListener("click", () => showKiosk(t.dataset.kioskTab)));
  }

  let bound = false;
  function bindApp() {
    if (bound) return;
    bound = true;
    bindTabs();
    showView("overview");
    showKiosk("experience");
    startLivePulse();

    ui.logoutBtn.addEventListener("click", () => logout());
    ui.refreshAllBtn.addEventListener("click", refreshAll);
    ui.globalDeviceReloadBtn.addEventListener("click", async () => { try { await loadDevicesOptions(); await refreshAll(); } catch (err) { setStatus(`Device refresh failed: ${err.message}`, "bad"); } });
    ui.globalDeviceSelector.addEventListener("change", async () => { state.selectedDeviceCode = String(ui.globalDeviceSelector.value || "").trim(); ui.deviceActionDeviceCode.value = state.selectedDeviceCode || ui.deviceActionDeviceCode.value; await refreshAll(); });
    ui.devicesIncludeInactive.addEventListener("change", loadDevices);

    ui.paymentsReloadBtn.addEventListener("click", loadPayments);
    ui.paymentsFilters.addEventListener("submit", async (e) => { e.preventDefault(); await loadPayments(); setStatus("Payments filters applied.", "ok"); });

    ui.reportsReloadBtn.addEventListener("click", loadReport);
    ui.reportHistoryReloadBtn.addEventListener("click", loadReportHistory);
    ui.reportHistoryFilters.addEventListener("submit", async (e) => { e.preventDefault(); await loadReportHistory(); setStatus("Report history filters applied.", "ok"); });
    ui.reportCleanupDryRunBtn.addEventListener("click", async () => { await runCleanup(true); await loadReportHistory(); });
    ui.reportCleanupRunBtn.addEventListener("click", async () => { if (!window.confirm("Run cleanup now?")) return; await runCleanup(false); await loadReportHistory(); });

    [ui.pricingA4Bw, ui.pricingA4Color, ui.pricingA3Bw, ui.pricingA3Color, ui.pricingCurrency, ui.pricingColorProfile, ui.pricingPaperProfile].forEach((el) => el.addEventListener("change", updatePricingPreview));
    ui.pricingReloadBtn.addEventListener("click", loadPricing);
    ui.pricingForm.addEventListener("submit", async (e) => { e.preventDefault(); await savePricing(); await Promise.all([loadPricing(), loadOverview(), loadDevices(), loadAvailability()]); setStatus("Pricing and capabilities saved.", "ok"); });

    ui.customerExperienceReloadBtn.addEventListener("click", async () => { await Promise.all([loadCX(), loadAvailability(), loadQrPack()]); setStatus("Customer controls reloaded.", "ok"); });
    ui.customerAvailabilityReloadBtn.addEventListener("click", loadAvailability);
    ui.cxHotspotSecurity.addEventListener("change", syncHotspotSecurityUi);
    ui.customerExperienceForm.addEventListener("submit", async (e) => { e.preventDefault(); await saveCX(); await Promise.all([loadAvailability(), loadQrPack(), loadPricing()]); setStatus("Customer controls saved.", "ok"); });

    const act = async (btn, name, msg, confirmText = "") => {
      if (confirmText && !window.confirm(confirmText)) return;
      btn.disabled = true;
      try {
        const r = await action(name);
        setStatus(`${msg}${r.status === "failed" ? " (action failed on device)." : ""}`, r.status === "failed" ? "bad" : "ok");
        await Promise.all([loadOverview(), loadDevices(), loadAvailability(), loadQrPack()]);
      } catch (err) {
        setStatus(`Device action failed: ${err.message}`, "bad");
      } finally { btn.disabled = false; }
    };

    ui.actionPauseKioskBtn.addEventListener("click", () => act(ui.actionPauseKioskBtn, "pause_kiosk", "Kiosk paused."));
    ui.actionResumeKioskBtn.addEventListener("click", () => act(ui.actionResumeKioskBtn, "resume_kiosk", "Kiosk resumed."));
    ui.actionApplyHotspotBtn.addEventListener("click", () => act(ui.actionApplyHotspotBtn, "apply_hotspot", "Hotspot apply command sent."));
    ui.actionDisableHotspotBtn.addEventListener("click", () => act(ui.actionDisableHotspotBtn, "disable_hotspot", "Hotspot disable command sent.", "Disable hotspot mode?"));
    ui.actionRestartAgentBtn.addEventListener("click", () => act(ui.actionRestartAgentBtn, "restart_agent", "Agent restart command sent."));
    ui.actionRestartApiBtn.addEventListener("click", () => act(ui.actionRestartApiBtn, "restart_api", "API restart command sent."));
    ui.actionRebootDeviceBtn.addEventListener("click", () => act(ui.actionRebootDeviceBtn, "reboot_device", "Device reboot command sent.", "Reboot this device now?"));

    ui.qrPackReloadBtn.addEventListener("click", loadQrPack);
    ui.qrCopyBtn.addEventListener("click", async () => { try { await navigator.clipboard.writeText(ui.qrEntryUrl.value || ""); setStatus("Customer entry URL copied.", "ok"); } catch { setStatus("Copy failed.", "bad"); } });
    ui.qrLanCopyBtn.addEventListener("click", async () => { try { await navigator.clipboard.writeText(ui.qrLanEntryUrl.value || ""); setStatus("LAN entry URL copied.", "ok"); } catch { setStatus("Copy failed.", "bad"); } });
    ui.wifiCopyBtn.addEventListener("click", async () => { try { await navigator.clipboard.writeText(ui.wifiQrPayload.value || ""); setStatus("Wi-Fi QR payload copied.", "ok"); } catch { setStatus("Copy failed.", "bad"); } });
    ui.qrOpenBtn.addEventListener("click", () => { if (ui.qrEntryUrl.value) window.open(ui.qrEntryUrl.value, "_blank", "noopener"); });

    ui.refundsReloadBtn.addEventListener("click", loadRefunds);
    ui.refundCreateForm.addEventListener("submit", async (e) => { e.preventDefault(); await api("/admin/refunds/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payment_id: ui.refundPaymentId.value.trim(), reason: ui.refundReason.value.trim(), requested_by: ui.refundRequestedBy.value.trim() || "operator" }) }); await Promise.all([loadRefunds(), loadPayments(), loadOverview()]); setStatus("Refund request created.", "ok"); });
    ui.refundFilters.addEventListener("submit", async (e) => { e.preventDefault(); await loadRefunds(); setStatus("Refund filters applied.", "ok"); });
    ui.refundsBody.addEventListener("click", async (e) => {
      const btn = e.target.closest("button[data-refund-action]");
      if (!btn) return;
      btn.disabled = true;
      try {
        await api(`/admin/refunds/${encodeURIComponent(btn.getAttribute("data-refund-id") || "")}/${btn.getAttribute("data-refund-action") || ""}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actor: ui.refundActorName.value.trim() || "operator", note: ui.refundDecisionNote.value.trim() }) });
        await Promise.all([loadRefunds(), loadPayments(), loadOverview()]);
        setStatus("Refund action completed.", "ok");
      } finally { btn.disabled = false; }
    });

    ui.usersReloadBtn.addEventListener("click", loadUsers);
    ui.userCreateForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await api("/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ full_name: ui.userCreateName.value.trim(), email: ui.userCreateEmail.value.trim(), role: ui.userCreateRole.value, password: ui.userCreatePassword.value.trim(), is_active: true }) });
      ui.userCreatePassword.value = "";
      await loadUsers();
      setStatus("Admin user created.", "ok");
    });
    ui.usersBody.addEventListener("click", async (e) => {
      const btn = e.target.closest("button[data-user-save]");
      if (!btn) return;
      const row = btn.closest("tr[data-user-id]");
      if (!row) return;
      btn.disabled = true;
      try {
        await api(`/admin/users/${encodeURIComponent(row.getAttribute("data-user-id") || "")}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ full_name: row.querySelector("[data-user-name]")?.value?.trim() || undefined, role: row.querySelector("[data-user-role]")?.value || undefined, is_active: boolVal(row.querySelector("[data-user-active]")?.value), new_password: row.querySelector("[data-user-password]")?.value?.trim() || undefined }) });
        await loadUsers();
        setStatus("Admin user updated.", "ok");
      } finally { btn.disabled = false; }
    });
  }

  function bindAuth() {
    ui.showForgotBtn.addEventListener("click", () => showAuth("forgot"));
    ui.showResetBtn.addEventListener("click", () => showAuth("reset"));
    ui.loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      setAuthStatus("Signing in...");
      try {
        await login(ui.loginEmail.value.trim(), ui.loginPassword.value);
        showApp();
        bindApp();
        await refreshAll();
      } catch (err) {
        setAuthStatus(`Sign in failed: ${err.message}`, "bad");
      }
    });
    ui.forgotForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const p = await api("/admin/auth/forgot-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: ui.forgotEmail.value.trim() }) }, false);
        setAuthStatus(`Reset request submitted.${p.preview_link ? ` Preview: ${p.preview_link}` : ""}`, "ok");
      } catch (err) {
        setAuthStatus(`Forgot password failed: ${err.message}`, "bad");
      }
    });
    ui.resetForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/admin/auth/reset-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: ui.resetToken.value.trim(), new_password: ui.resetPassword.value }) }, false);
        setAuthStatus("Password reset successful. Please sign in.", "ok");
      } catch (err) {
        setAuthStatus(`Reset failed: ${err.message}`, "bad");
      }
    });
  }

  async function init() {
    bindAuth();
    const params = new URLSearchParams(window.location.search);
    if (params.get("mode") === "reset") {
      showAuth("reset");
      ui.resetToken.value = params.get("token") || "";
    }
    const ok = await restoreSession();
    if (ok) {
      showApp();
      bindApp();
      await refreshAll();
    } else {
      showAuth();
    }
  }

  init().catch((err) => setAuthStatus(`Initialization failed: ${err.message}`, "bad"));
})();
