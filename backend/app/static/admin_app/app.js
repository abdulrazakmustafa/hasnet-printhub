(function () {
  const API_BASE = `${window.location.origin}/api/v1`;

  const $ = (id) => document.getElementById(id);
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

    qrEntryUrl: $("qrEntryUrl"),
    qrPreview: $("qrPreview"),
    qrHint: $("qrHint"),
    qrCopyBtn: $("qrCopyBtn"),
    qrOpenBtn: $("qrOpenBtn"),
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
      || value === "online"
      || value === "active"
      || value === "resolved"
      || value === "ready"
      || value === "ok"
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

  function customerEntryUrl() {
    return `${window.location.origin}/customer-start`;
  }

  function renderQrEntry() {
    const entryUrl = customerEntryUrl();
    ui.qrEntryUrl.value = entryUrl;
    ui.qrPreview.src = `https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=${encodeURIComponent(entryUrl)}`;
    ui.qrPreview.onerror = () => {
      ui.qrHint.textContent = "QR preview unavailable now; URL is ready to use in any QR generator.";
    };
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
    tbody.innerHTML = rowsHtml || `<tr><td colspan="20">No data</td></tr>`;
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
      ]);
      renderQrEntry();
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
        await loadIncidents();
        await loadOverview();
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

    ui.qrCopyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(ui.qrEntryUrl.value);
        setStatus("QR entry URL copied.", "ok");
      } catch (_err) {
        setStatus("Copy failed. Please copy URL manually.", "bad");
      }
    });

    ui.qrOpenBtn.addEventListener("click", () => {
      window.open(ui.qrEntryUrl.value, "_blank", "noopener");
    });
  }

  async function init() {
    bindTabs();
    bindEvents();
    showView("overview");
    renderQrEntry();
    await refreshAll();
  }

  init().catch((err) => {
    setStatus(`Initialization failed: ${err.message}`, "bad");
  });
})();
