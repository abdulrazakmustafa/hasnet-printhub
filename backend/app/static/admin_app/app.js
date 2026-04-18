(function () {
  const API_BASE = `${window.location.origin}/api/v1`;

  const $ = (id) => document.getElementById(id);
  const state = {
    customerExperience: null,
    qrPack: null,
  };

  const ui = {
    tabs: document.querySelectorAll(".tab"),
    views: document.querySelectorAll("[data-view-panel]"),
    status: $("status"),
    refreshAllBtn: $("refreshAllBtn"),

    kpiConfirmedPayments: $("kpiConfirmedPayments"),
    kpiConfirmedAmount: $("kpiConfirmedAmount"),
    kpiPrintedJobs: $("kpiPrintedJobs"),
    kpiActiveDevices: $("kpiActiveDevices"),
    kpiPendingIncidents: $("kpiPendingIncidents"),
    kpiEscalatedIncidents: $("kpiEscalatedIncidents"),
    overviewRecentPaymentsBody: $("overviewRecentPaymentsBody"),
    overviewIncidentsBody: $("overviewIncidentsBody"),

    devicesIncludeInactive: $("devicesIncludeInactive"),
    devicesBody: $("devicesBody"),

    paymentsFilters: $("paymentsFilters"),
    paymentsReloadBtn: $("paymentsReloadBtn"),
    paymentsStatus: $("paymentsStatus"),
    paymentsMethod: $("paymentsMethod"),
    paymentsLifecycle: $("paymentsLifecycle"),
    paymentsProvider: $("paymentsProvider"),
    paymentsDeviceCode: $("paymentsDeviceCode"),
    paymentsLimit: $("paymentsLimit"),
    paymentsBody: $("paymentsBody"),

    incidentsFilters: $("incidentsFilters"),
    incidentsReloadBtn: $("incidentsReloadBtn"),
    incidentsEscalatedOnly: $("incidentsEscalatedOnly"),
    incidentsMethod: $("incidentsMethod"),
    incidentsDeviceCode: $("incidentsDeviceCode"),
    incidentsLimit: $("incidentsLimit"),
    incidentsBody: $("incidentsBody"),
    reconcileBtn: $("reconcileBtn"),

    alertsFilters: $("alertsFilters"),
    alertsReloadBtn: $("alertsReloadBtn"),
    alertsStatus: $("alertsStatus"),
    alertsSeverity: $("alertsSeverity"),
    alertsDeviceCode: $("alertsDeviceCode"),
    alertsLimit: $("alertsLimit"),
    alertsBody: $("alertsBody"),

    reportsReloadBtn: $("reportsReloadBtn"),
    reportPaymentsTotal: $("reportPaymentsTotal"),
    reportPaymentsConfirmed: $("reportPaymentsConfirmed"),
    reportPaymentsPending: $("reportPaymentsPending"),
    reportPaymentsFailed: $("reportPaymentsFailed"),
    reportJobsPrinted: $("reportJobsPrinted"),
    reportJobsProgress: $("reportJobsProgress"),
    reportDevicesActive: $("reportDevicesActive"),
    reportDevicesOnline: $("reportDevicesOnline"),

    pricingForm: $("pricingForm"),
    pricingReloadBtn: $("pricingReloadBtn"),
    pricingBw: $("pricingBw"),
    pricingColor: $("pricingColor"),
    pricingCurrency: $("pricingCurrency"),
    pricingPreview: $("pricingPreview"),

    customerExperienceForm: $("customerExperienceForm"),
    customerExperienceReloadBtn: $("customerExperienceReloadBtn"),
    customerAvailabilityReloadBtn: $("customerAvailabilityReloadBtn"),
    customerAvailabilityPreview: $("customerAvailabilityPreview"),

    cxActiveDeviceCode: $("cxActiveDeviceCode"),
    cxSiteStripText: $("cxSiteStripText"),
    cxBrandTitle: $("cxBrandTitle"),
    cxBrandNote: $("cxBrandNote"),
    cxWelcomeTitle: $("cxWelcomeTitle"),
    cxWelcomeLead: $("cxWelcomeLead"),
    cxSupportPhone: $("cxSupportPhone"),
    cxChip1: $("cxChip1"),
    cxChip2: $("cxChip2"),
    cxChip3: $("cxChip3"),
    cxBrandBlue: $("cxBrandBlue"),
    cxBrandOrange: $("cxBrandOrange"),
    cxHidePaymentMethod: $("cxHidePaymentMethod"),
    cxShowStepper: $("cxShowStepper"),
    cxDefaultPaymentMethod: $("cxDefaultPaymentMethod"),
    cxUploadsEnabled: $("cxUploadsEnabled"),
    cxPaymentsEnabled: $("cxPaymentsEnabled"),
    cxPauseReason: $("cxPauseReason"),
    cxPrinterUnreadyMessage: $("cxPrinterUnreadyMessage"),
    cxHotspotEnabled: $("cxHotspotEnabled"),
    cxHotspotSsid: $("cxHotspotSsid"),
    cxHotspotPassphrase: $("cxHotspotPassphrase"),
    cxHotspotSecurity: $("cxHotspotSecurity"),

    deviceActionForm: $("deviceActionForm"),
    deviceActionDeviceCode: $("deviceActionDeviceCode"),
    deviceActionSudoPassword: $("deviceActionSudoPassword"),
    deviceActionNote: $("deviceActionNote"),
    actionPauseKioskBtn: $("actionPauseKioskBtn"),
    actionResumeKioskBtn: $("actionResumeKioskBtn"),
    actionRestartAgentBtn: $("actionRestartAgentBtn"),
    actionRestartApiBtn: $("actionRestartApiBtn"),
    actionRebootDeviceBtn: $("actionRebootDeviceBtn"),

    qrPackReloadBtn: $("qrPackReloadBtn"),
    qrEntryUrl: $("qrEntryUrl"),
    wifiQrPayload: $("wifiQrPayload"),
    qrPreview: $("qrPreview"),
    wifiQrPreview: $("wifiQrPreview"),
    qrHint: $("qrHint"),
    qrCopyBtn: $("qrCopyBtn"),
    wifiCopyBtn: $("wifiCopyBtn"),
    qrOpenBtn: $("qrOpenBtn"),

    refundsReloadBtn: $("refundsReloadBtn"),
    refundCreateForm: $("refundCreateForm"),
    refundPaymentId: $("refundPaymentId"),
    refundReason: $("refundReason"),
    refundRequestedBy: $("refundRequestedBy"),
    refundFilters: $("refundFilters"),
    refundStatusFilter: $("refundStatusFilter"),
    refundPaymentFilter: $("refundPaymentFilter"),
    refundActorName: $("refundActorName"),
    refundDecisionNote: $("refundDecisionNote"),
    refundsBody: $("refundsBody"),
  };

  function setStatus(message, tone) {
    ui.status.textContent = message || "";
    if (tone === "bad") {
      ui.status.style.color = "#d64566";
    } else if (tone === "ok") {
      ui.status.style.color = "#2f9958";
    } else {
      ui.status.style.color = "#506193";
    }
  }

  function parseBooleanInput(raw) {
    return String(raw || "").toLowerCase() === "true";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString();
  }

  function toMoney(value, currency) {
    const numeric = Number(value || 0);
    const safeCurrency = String(currency || "TZS").toUpperCase();
    return `${numeric.toFixed(0)} ${safeCurrency}`;
  }

  function chipTone(raw) {
    const value = String(raw || "").toLowerCase();
    if (
      value.includes("confirmed")
      || value.includes("printed")
      || value.includes("online")
      || value.includes("active")
      || value.includes("resolved")
      || value.includes("ready")
      || value.includes("ok")
      || value.includes("executed")
      || value.includes("approved")
    ) {
      return "ok";
    }
    if (
      value.includes("pending")
      || value.includes("warning")
      || value.includes("processing")
      || value.includes("printing")
      || value.includes("in_progress")
      || value.includes("awaiting")
      || value.includes("degraded")
      || value.includes("requested")
    ) {
      return "warn";
    }
    if (
      value.includes("failed")
      || value.includes("offline")
      || value.includes("critical")
      || value.includes("expired")
      || value.includes("escalated")
      || value.includes("blocked")
      || value.includes("rejected")
    ) {
      return "bad";
    }
    return "";
  }

  function chip(text) {
    const tone = chipTone(text);
    return `<span class="chip ${tone}">${escapeHtml(text || "-")}</span>`;
  }

  function paymentPayerLabel(item) {
    const name = String(item.customer_name || "").trim();
    const msisdn = String(item.customer_msisdn || "").trim();
    if (name && msisdn) return `${name} | ${msisdn}`;
    if (name) return name;
    if (msisdn) return msisdn;
    return "-";
  }

  function paymentDocumentLabel(item) {
    const documentName = String(item.document_name || "").trim();
    const pages = Number(item.pages || 0);
    const copies = Number(item.copies || 0);
    const color = String(item.color_mode || "").trim();
    const pieces = [];
    if (pages > 0) pieces.push(`${pages}p`);
    if (copies > 0) pieces.push(`${copies}x`);
    if (color) pieces.push(color);
    if (!documentName && pieces.length < 1) return "-";
    if (!documentName) return pieces.join(" | ");
    if (pieces.length < 1) return documentName;
    return `${documentName} (${pieces.join(" | ")})`;
  }

  function queryString(params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      qs.set(key, String(value));
    });
    return qs.toString();
  }

  async function call(path, options) {
    const response = await fetch(`${API_BASE}${path}`, options);
    let payload = null;
    try {
      payload = await response.json();
    } catch (_err) {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return payload;
  }

  function showView(view) {
    ui.tabs.forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.view === view);
    });
    ui.views.forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.viewPanel === view);
    });
  }

  function setRows(tbody, rowsHtml) {
    tbody.innerHTML = rowsHtml || "<tr><td colspan=\"20\">No data</td></tr>";
  }

  function currentDeviceCode() {
    const fromAction = String(ui.deviceActionDeviceCode.value || "").trim();
    if (fromAction) return fromAction;
    const fromConfig = String(ui.cxActiveDeviceCode.value || "").trim();
    if (fromConfig) return fromConfig;
    if (state.customerExperience?.active_device_code) return String(state.customerExperience.active_device_code);
    return "pi-kiosk-001";
  }

  function fillCustomerExperienceForm(config) {
    state.customerExperience = config || {};
    const theme = config.theme || {};
    const content = config.content || {};
    const flow = config.flow || {};
    const operations = config.operations || {};
    const hotspot = config.hotspot || {};
    const chips = Array.isArray(config.chips) ? config.chips : [];

    ui.cxActiveDeviceCode.value = config.active_device_code || "pi-kiosk-001";
    ui.cxSiteStripText.value = config.site_strip_text || "";
    ui.cxBrandTitle.value = content.brand_title || "";
    ui.cxBrandNote.value = content.brand_note || "";
    ui.cxWelcomeTitle.value = content.welcome_title || "";
    ui.cxWelcomeLead.value = content.welcome_lead || "";
    ui.cxSupportPhone.value = content.support_phone || "";
    ui.cxChip1.value = chips[0] || "";
    ui.cxChip2.value = chips[1] || "";
    ui.cxChip3.value = chips[2] || "";

    ui.cxBrandBlue.value = theme.brand_blue || "#272365";
    ui.cxBrandOrange.value = theme.brand_orange || "#f47c20";

    ui.cxHidePaymentMethod.value = String(flow.hide_payment_method !== false);
    ui.cxShowStepper.value = String(flow.show_stepper !== false);
    ui.cxDefaultPaymentMethod.value = flow.default_payment_method || "mpesa";

    ui.cxUploadsEnabled.value = String(operations.uploads_enabled !== false);
    ui.cxPaymentsEnabled.value = String(operations.payments_enabled !== false);
    ui.cxPauseReason.value = operations.pause_reason || "";
    ui.cxPrinterUnreadyMessage.value = operations.printer_unready_message || "";

    ui.cxHotspotEnabled.value = String(Boolean(hotspot.enabled));
    ui.cxHotspotSsid.value = hotspot.ssid || "";
    ui.cxHotspotPassphrase.value = hotspot.passphrase || "";
    ui.cxHotspotSecurity.value = hotspot.wifi_security || "WPA";

    const activeCode = currentDeviceCode();
    ui.deviceActionDeviceCode.value = activeCode;
    ui.paymentsDeviceCode.placeholder = activeCode;
    ui.incidentsDeviceCode.placeholder = activeCode;
    ui.alertsDeviceCode.placeholder = activeCode;
  }

  function customerExperiencePayloadFromForm() {
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
      chips: [ui.cxChip1.value, ui.cxChip2.value, ui.cxChip3.value]
        .map((item) => String(item || "").trim())
        .filter(Boolean),
      theme: {
        ...(state.customerExperience?.theme || {}),
        brand_blue: String(ui.cxBrandBlue.value || "").trim(),
        brand_orange: String(ui.cxBrandOrange.value || "").trim(),
      },
      flow: {
        ...(state.customerExperience?.flow || {}),
        hide_payment_method: parseBooleanInput(ui.cxHidePaymentMethod.value),
        show_stepper: parseBooleanInput(ui.cxShowStepper.value),
        default_payment_method: String(ui.cxDefaultPaymentMethod.value || "mpesa").toLowerCase(),
      },
      operations: {
        ...(state.customerExperience?.operations || {}),
        uploads_enabled: parseBooleanInput(ui.cxUploadsEnabled.value),
        payments_enabled: parseBooleanInput(ui.cxPaymentsEnabled.value),
        pause_reason: String(ui.cxPauseReason.value || "").trim(),
        printer_unready_message: String(ui.cxPrinterUnreadyMessage.value || "").trim(),
      },
      hotspot: {
        ...(state.customerExperience?.hotspot || {}),
        enabled: parseBooleanInput(ui.cxHotspotEnabled.value),
        ssid: String(ui.cxHotspotSsid.value || "").trim(),
        passphrase: String(ui.cxHotspotPassphrase.value || "").trim(),
        wifi_security: String(ui.cxHotspotSecurity.value || "WPA").toUpperCase(),
      },
    };
  }

  function setQrPreview(imgElement, value) {
    if (!value) {
      imgElement.removeAttribute("src");
      return;
    }
    imgElement.src = `https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=${encodeURIComponent(value)}`;
  }
  async function loadOverview() {
    const payload = await call("/admin/dashboard/snapshot?recent_payments_limit=10&pending_incidents_limit=10", { method: "GET" });
    const kpis = payload.kpis || {};
    ui.kpiConfirmedPayments.textContent = String(kpis.confirmed_payments_today ?? 0);
    ui.kpiConfirmedAmount.textContent = toMoney(kpis.confirmed_amount_today, payload.pricing ? payload.pricing.currency : "TZS");
    ui.kpiPrintedJobs.textContent = String(kpis.printed_jobs_today ?? 0);
    ui.kpiActiveDevices.textContent = String(kpis.active_devices ?? 0);
    ui.kpiPendingIncidents.textContent = String(kpis.pending_incidents ?? 0);
    ui.kpiEscalatedIncidents.textContent = String(kpis.escalated_pending_incidents ?? 0);

    const payments = (payload.recent_payments && payload.recent_payments.items) || [];
    const paymentRows = payments.map((item) => `
      <tr>
        <td>${escapeHtml(formatDate(item.requested_at))}</td>
        <td>${chip(item.method)}</td>
        <td>${chip(item.status)}</td>
        <td>${escapeHtml(toMoney(item.amount, item.currency))}</td>
        <td>${escapeHtml(item.device_code || "-")}</td>
      </tr>
    `).join("");
    setRows(ui.overviewRecentPaymentsBody, paymentRows);

    const incidents = (payload.pending_incidents && payload.pending_incidents.items) || [];
    const incidentRows = incidents.map((item) => `
      <tr>
        <td>${escapeHtml(item.provider_request_id || "-")}</td>
        <td>${chip(item.method)}</td>
        <td>${escapeHtml(String(item.pending_minutes ?? "-"))}</td>
        <td>${chip(item.escalated ? "escalated" : "normal")}</td>
        <td>${escapeHtml(item.device_code || "-")}</td>
      </tr>
    `).join("");
    setRows(ui.overviewIncidentsBody, incidentRows);
  }

  async function loadDevices() {
    const includeInactive = ui.devicesIncludeInactive.checked ? "true" : "false";
    const payload = await call(`/admin/devices?include_inactive=${includeInactive}`, { method: "GET" });
    const rows = (payload.items || []).map((item) => `
      <tr>
        <td>${escapeHtml(item.device_code)}</td>
        <td>${escapeHtml(item.site_name || "-")}</td>
        <td>${chip(item.status)}</td>
        <td>${chip(item.printer_status)}</td>
        <td>${escapeHtml(formatDate(item.last_seen_at))}</td>
        <td>${escapeHtml(String(item.active_alerts ?? 0))}</td>
        <td>${escapeHtml(`T:${item.jobs.total} P:${item.jobs.printed} F:${item.jobs.failed}`)}</td>
      </tr>
    `).join("");
    setRows(ui.devicesBody, rows);
  }

  function paymentsQuery() {
    return queryString({
      limit: ui.paymentsLimit.value || 50,
      status: ui.paymentsStatus.value,
      method: ui.paymentsMethod.value,
      lifecycle: ui.paymentsLifecycle.value,
      provider: ui.paymentsProvider.value.trim(),
      device_code: ui.paymentsDeviceCode.value.trim(),
    });
  }

  async function loadPayments() {
    const payload = await call(`/admin/payments?${paymentsQuery()}`, { method: "GET" });
    const rows = (payload.items || []).map((item) => `
      <tr>
        <td>${escapeHtml(formatDate(item.requested_at))}</td>
        <td>${escapeHtml(item.provider_request_id || "-")}</td>
        <td>${chip(item.method)}</td>
        <td>${chip(item.status)}</td>
        <td>${chip(item.lifecycle || "other")}</td>
        <td>${escapeHtml(toMoney(item.amount, item.currency))}</td>
        <td>${escapeHtml(paymentPayerLabel(item))}</td>
        <td>${escapeHtml(paymentDocumentLabel(item))}</td>
        <td>${escapeHtml(item.print_job_id)}</td>
        <td>${escapeHtml(item.device_code || "-")}</td>
      </tr>
    `).join("");
    setRows(ui.paymentsBody, rows);
  }

  function incidentsQuery() {
    return queryString({
      limit: ui.incidentsLimit.value || 50,
      escalated_only: ui.incidentsEscalatedOnly.value,
      method: ui.incidentsMethod.value,
      device_code: ui.incidentsDeviceCode.value.trim(),
    });
  }

  async function loadIncidents() {
    const payload = await call(`/admin/payments/pending-incidents?${incidentsQuery()}`, { method: "GET" });
    const rows = (payload.items || []).map((item) => `
      <tr>
        <td>${escapeHtml(item.provider_request_id || "-")}</td>
        <td>${chip(item.method)}</td>
        <td>${chip(item.status)}</td>
        <td>${escapeHtml(String(item.pending_minutes ?? "-"))}</td>
        <td>${chip(item.escalated ? "escalated" : "normal")}</td>
        <td>${escapeHtml(item.recommended_action || "-")}</td>
      </tr>
    `).join("");
    setRows(ui.incidentsBody, rows);
  }

  function alertsQuery() {
    return queryString({
      limit: ui.alertsLimit.value || 50,
      status: ui.alertsStatus.value,
      severity: ui.alertsSeverity.value,
      device_code: ui.alertsDeviceCode.value.trim(),
    });
  }

  async function loadAlerts() {
    const payload = await call(`/alerts?${alertsQuery()}`, { method: "GET" });
    const rows = (payload.items || []).map((item) => `
      <tr>
        <td>${escapeHtml(formatDate(item.last_seen_at))}</td>
        <td>${escapeHtml(item.title || "-")}</td>
        <td>${chip(item.severity)}</td>
        <td>${chip(item.status)}</td>
        <td>${escapeHtml(item.device_code || "-")}</td>
      </tr>
    `).join("");
    setRows(ui.alertsBody, rows);
  }

  async function loadReport() {
    const payload = await call("/admin/reports/today", { method: "GET" });
    const payments = payload.payments || {};
    const jobs = payload.jobs || {};
    const devices = payload.devices || {};
    ui.reportPaymentsTotal.textContent = String(payments.total ?? 0);
    ui.reportPaymentsConfirmed.textContent = String(payments.confirmed ?? 0);
    ui.reportPaymentsPending.textContent = String(payments.pending ?? 0);
    ui.reportPaymentsFailed.textContent = String(payments.failed ?? 0);
    ui.reportJobsPrinted.textContent = String(jobs.printed ?? 0);
    ui.reportJobsProgress.textContent = String(jobs.in_progress ?? 0);
    ui.reportDevicesActive.textContent = String(devices.active ?? 0);
    ui.reportDevicesOnline.textContent = String(devices.online ?? 0);
  }

  async function loadPricing() {
    const payload = await call("/admin/pricing", { method: "GET" });
    ui.pricingBw.value = payload.bw_price_per_page;
    ui.pricingColor.value = payload.color_price_per_page;
    ui.pricingCurrency.value = payload.currency;
    ui.pricingPreview.textContent = `BW: ${payload.bw_price_per_page} ${payload.currency} | Color: ${payload.color_price_per_page} ${payload.currency}`;
  }

  async function savePricing() {
    const body = {
      bw_price_per_page: Number(ui.pricingBw.value || 0),
      color_price_per_page: Number(ui.pricingColor.value || 0),
      currency: String(ui.pricingCurrency.value || "").trim().toUpperCase(),
    };
    const payload = await call("/admin/pricing", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    ui.pricingPreview.textContent = `BW: ${payload.bw_price_per_page} ${payload.currency} | Color: ${payload.color_price_per_page} ${payload.currency}`;
  }

  async function runReconcile() {
    await call("/admin/payments/reconcile?limit=100", { method: "POST" });
  }

  async function loadCustomerExperience() {
    const payload = await call("/admin/customer-experience", { method: "GET" });
    fillCustomerExperienceForm(payload);
  }

  async function saveCustomerExperience() {
    const payload = customerExperiencePayloadFromForm();
    const saved = await call("/admin/customer-experience", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    });
    fillCustomerExperienceForm(saved);
  }

  async function loadCustomerAvailability() {
    const code = currentDeviceCode();
    const payload = await call(`/admin/customer-availability?${queryString({ device_code: code })}`, { method: "GET" });
    const availability = payload.availability || {};
    ui.customerAvailabilityPreview.textContent = [
      `Device: ${payload.device_code || "-"}`,
      `Upload: ${availability.can_upload ? "enabled" : "blocked"}`,
      `Payment: ${availability.can_pay ? "enabled" : "blocked"}`,
      `Reason: ${availability.reason_code || "-"}`,
      `Message: ${availability.message || "-"}`,
    ].join(" | ");
  }

  async function loadQrPack() {
    const code = currentDeviceCode();
    const payload = await call(`/admin/devices/${encodeURIComponent(code)}/qr-pack`, { method: "GET" });
    state.qrPack = payload;
    ui.qrEntryUrl.value = payload.entry_url || "";
    ui.wifiQrPayload.value = payload.wifi?.wifi_qr_payload || "";
    setQrPreview(ui.qrPreview, ui.qrEntryUrl.value);
    setQrPreview(ui.wifiQrPreview, ui.wifiQrPayload.value);
    ui.qrHint.textContent = payload.notes?.join(" ") || "Print both QR codes for kiosk onboarding.";
  }

  async function runDeviceAction(action) {
    const deviceCode = currentDeviceCode();
    const body = {
      action,
      sudo_password: String(ui.deviceActionSudoPassword.value || ""),
      note: String(ui.deviceActionNote.value || ""),
      confirm_reboot: action === "reboot_device",
    };
    const result = await call(`/admin/devices/${encodeURIComponent(deviceCode)}/actions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (action === "pause_kiosk" || action === "resume_kiosk") {
      await loadCustomerExperience();
      await loadCustomerAvailability();
    }
    return result;
  }

  function refundsQuery() {
    return queryString({
      status: ui.refundStatusFilter.value.trim(),
      payment_id: ui.refundPaymentFilter.value.trim(),
    });
  }

  async function loadRefunds() {
    const payload = await call(`/admin/refunds?${refundsQuery()}`, { method: "GET" });
    const rows = (payload.items || []).map((item) => {
      let actions = "-";
      if (item.status === "requested") {
        actions = `
          <div class="inline-actions">
            <button data-refund-action="approve" data-refund-id="${escapeHtml(item.refund_id)}" type="button">Approve</button>
            <button data-refund-action="reject" data-refund-id="${escapeHtml(item.refund_id)}" type="button" class="danger">Reject</button>
          </div>
        `;
      } else if (item.status === "approved") {
        actions = `
          <div class="inline-actions">
            <button data-refund-action="execute" data-refund-id="${escapeHtml(item.refund_id)}" type="button">Execute</button>
            <button data-refund-action="reject" data-refund-id="${escapeHtml(item.refund_id)}" type="button" class="danger">Reject</button>
          </div>
        `;
      }
      return `
        <tr>
          <td>${escapeHtml(item.refund_id || "-")}</td>
          <td>${escapeHtml(item.payment_id || "-")}</td>
          <td>${chip(item.status || "-")}</td>
          <td>${escapeHtml(item.reason || "-")}</td>
          <td>${escapeHtml(item.requested_by || "-")}</td>
          <td>${escapeHtml(formatDate(item.updated_at || item.created_at))}</td>
          <td>${actions}</td>
        </tr>
      `;
    }).join("");
    setRows(ui.refundsBody, rows);
  }

  async function createRefund() {
    const body = {
      payment_id: String(ui.refundPaymentId.value || "").trim(),
      reason: String(ui.refundReason.value || "").trim(),
      requested_by: String(ui.refundRequestedBy.value || "").trim() || "operator",
    };
    if (!body.payment_id || !body.reason) {
      throw new Error("Payment ID and reason are required for refund request.");
    }
    await call("/admin/refunds/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function runRefundDecision(refundId, action) {
    const body = {
      actor: String(ui.refundActorName.value || "").trim() || "operator",
      note: String(ui.refundDecisionNote.value || "").trim(),
    };
    await call(`/admin/refunds/${encodeURIComponent(refundId)}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function refreshAll() {
    setStatus("Refreshing dashboard...", "");
    try {
      await Promise.all([
        loadOverview(),
        loadDevices(),
        loadPayments(),
        loadIncidents(),
        loadAlerts(),
        loadReport(),
        loadPricing(),
        loadCustomerExperience(),
        loadCustomerAvailability(),
        loadQrPack(),
        loadRefunds(),
      ]);
      setStatus("All admin panels refreshed.", "ok");
    } catch (err) {
      setStatus(`Refresh failed: ${err.message}`, "bad");
    }
  }

  function bindTabs() {
    ui.tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        showView(tab.dataset.view);
      });
    });
  }

  function bindEvents() {
    ui.refreshAllBtn.addEventListener("click", refreshAll);

    ui.devicesIncludeInactive.addEventListener("change", async () => {
      try {
        await loadDevices();
        setStatus("Devices reloaded.", "ok");
      } catch (err) {
        setStatus(`Devices reload failed: ${err.message}`, "bad");
      }
    });

    ui.paymentsReloadBtn.addEventListener("click", async () => {
      try {
        await loadPayments();
        setStatus("Payments reloaded.", "ok");
      } catch (err) {
        setStatus(`Payments reload failed: ${err.message}`, "bad");
      }
    });
    ui.paymentsFilters.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await loadPayments();
        setStatus("Payments filters applied.", "ok");
      } catch (err) {
        setStatus(`Payments query failed: ${err.message}`, "bad");
      }
    });

    ui.incidentsReloadBtn.addEventListener("click", async () => {
      try {
        await loadIncidents();
        setStatus("Incidents reloaded.", "ok");
      } catch (err) {
        setStatus(`Incidents reload failed: ${err.message}`, "bad");
      }
    });
    ui.incidentsFilters.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await loadIncidents();
        setStatus("Incident filters applied.", "ok");
      } catch (err) {
        setStatus(`Incidents query failed: ${err.message}`, "bad");
      }
    });
    ui.reconcileBtn.addEventListener("click", async () => {
      ui.reconcileBtn.disabled = true;
      try {
        await runReconcile();
        await Promise.all([loadIncidents(), loadOverview(), loadPayments()]);
        setStatus("Reconcile completed and incident list refreshed.", "ok");
      } catch (err) {
        setStatus(`Reconcile failed: ${err.message}`, "bad");
      } finally {
        ui.reconcileBtn.disabled = false;
      }
    });

    ui.alertsReloadBtn.addEventListener("click", async () => {
      try {
        await loadAlerts();
        setStatus("Alerts reloaded.", "ok");
      } catch (err) {
        setStatus(`Alerts reload failed: ${err.message}`, "bad");
      }
    });
    ui.alertsFilters.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await loadAlerts();
        setStatus("Alert filters applied.", "ok");
      } catch (err) {
        setStatus(`Alerts query failed: ${err.message}`, "bad");
      }
    });

    ui.reportsReloadBtn.addEventListener("click", async () => {
      try {
        await loadReport();
        setStatus("Report reloaded.", "ok");
      } catch (err) {
        setStatus(`Report reload failed: ${err.message}`, "bad");
      }
    });

    ui.pricingReloadBtn.addEventListener("click", async () => {
      try {
        await loadPricing();
        setStatus("Pricing reloaded.", "ok");
      } catch (err) {
        setStatus(`Pricing reload failed: ${err.message}`, "bad");
      }
    });
    ui.pricingForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await savePricing();
        setStatus("Pricing saved successfully.", "ok");
      } catch (err) {
        setStatus(`Pricing save failed: ${err.message}`, "bad");
      }
    });

    ui.customerExperienceReloadBtn.addEventListener("click", async () => {
      try {
        await loadCustomerExperience();
        await Promise.all([loadCustomerAvailability(), loadQrPack()]);
        setStatus("Customer controls reloaded.", "ok");
      } catch (err) {
        setStatus(`Customer controls reload failed: ${err.message}`, "bad");
      }
    });
    ui.customerAvailabilityReloadBtn.addEventListener("click", async () => {
      try {
        await loadCustomerAvailability();
        setStatus("Customer availability refreshed.", "ok");
      } catch (err) {
        setStatus(`Customer availability refresh failed: ${err.message}`, "bad");
      }
    });
    ui.customerExperienceForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await saveCustomerExperience();
        await Promise.all([loadCustomerAvailability(), loadQrPack()]);
        setStatus("Customer controls saved.", "ok");
      } catch (err) {
        setStatus(`Save customer controls failed: ${err.message}`, "bad");
      }
    });

    const handleDeviceAction = async (button, action, successMessage) => {
      button.disabled = true;
      try {
        const result = await runDeviceAction(action);
        setStatus(`${successMessage}${result.status === "failed" ? " (action failed on device)." : ""}`, result.status === "failed" ? "bad" : "ok");
      } catch (err) {
        setStatus(`Device action failed: ${err.message}`, "bad");
      } finally {
        button.disabled = false;
      }
    };

    ui.actionPauseKioskBtn.addEventListener("click", () => {
      handleDeviceAction(ui.actionPauseKioskBtn, "pause_kiosk", "Kiosk paused.");
    });
    ui.actionResumeKioskBtn.addEventListener("click", () => {
      handleDeviceAction(ui.actionResumeKioskBtn, "resume_kiosk", "Kiosk resumed.");
    });
    ui.actionRestartAgentBtn.addEventListener("click", () => {
      handleDeviceAction(ui.actionRestartAgentBtn, "restart_agent", "Agent restart command sent.");
    });
    ui.actionRestartApiBtn.addEventListener("click", () => {
      handleDeviceAction(ui.actionRestartApiBtn, "restart_api", "API restart command sent.");
    });
    ui.actionRebootDeviceBtn.addEventListener("click", () => {
      const confirmed = window.confirm("Reboot this device now?");
      if (!confirmed) return;
      handleDeviceAction(ui.actionRebootDeviceBtn, "reboot_device", "Device reboot command sent.");
    });

    ui.deviceActionForm.addEventListener("submit", (event) => {
      event.preventDefault();
    });

    ui.qrPackReloadBtn.addEventListener("click", async () => {
      try {
        await loadQrPack();
        setStatus("QR pack reloaded.", "ok");
      } catch (err) {
        setStatus(`QR pack reload failed: ${err.message}`, "bad");
      }
    });
    ui.qrCopyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(ui.qrEntryUrl.value || "");
        setStatus("Customer entry URL copied.", "ok");
      } catch (_err) {
        setStatus("Copy failed. Please copy manually.", "bad");
      }
    });
    ui.wifiCopyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(ui.wifiQrPayload.value || "");
        setStatus("Wi-Fi QR payload copied.", "ok");
      } catch (_err) {
        setStatus("Copy failed. Please copy manually.", "bad");
      }
    });
    ui.qrOpenBtn.addEventListener("click", () => {
      if (!ui.qrEntryUrl.value) return;
      window.open(ui.qrEntryUrl.value, "_blank", "noopener");
    });

    ui.refundsReloadBtn.addEventListener("click", async () => {
      try {
        await loadRefunds();
        setStatus("Refund list reloaded.", "ok");
      } catch (err) {
        setStatus(`Refund list reload failed: ${err.message}`, "bad");
      }
    });
    ui.refundCreateForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await createRefund();
        await Promise.all([loadRefunds(), loadPayments()]);
        setStatus("Refund request created.", "ok");
      } catch (err) {
        setStatus(`Refund create failed: ${err.message}`, "bad");
      }
    });
    ui.refundFilters.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await loadRefunds();
        setStatus("Refund filters applied.", "ok");
      } catch (err) {
        setStatus(`Refund query failed: ${err.message}`, "bad");
      }
    });
    ui.refundsBody.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-refund-action]");
      if (!button) return;
      const action = button.getAttribute("data-refund-action");
      const refundId = button.getAttribute("data-refund-id");
      if (!action || !refundId) return;
      button.disabled = true;
      try {
        await runRefundDecision(refundId, action);
        await Promise.all([loadRefunds(), loadPayments()]);
        setStatus(`Refund ${action} completed.`, "ok");
      } catch (err) {
        setStatus(`Refund ${action} failed: ${err.message}`, "bad");
      } finally {
        button.disabled = false;
      }
    });
  }

  async function init() {
    bindTabs();
    bindEvents();
    showView("overview");
    await refreshAll();
  }

  init().catch((err) => {
    setStatus(`Initialization failed: ${err.message}`, "bad");
  });
})();
