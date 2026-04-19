(function () {
  const API_BASE = `${window.location.origin}/api/v1`;
  const DEFAULT_DEVICE_CODE = "pi-kiosk-001";
  const DEFAULT_PAYMENT_METHOD = "mpesa";
  const POLL_INTERVAL_MS = 5000;
  const AVAILABILITY_REFRESH_MS = 12000;
  const URL_PARAMS = new URLSearchParams(window.location.search);
  const QA_MODE = URL_PARAMS.get("qa") === "1";
  const STEP_LABELS = {
    1: "Upload",
    2: "Print Options",
    3: "Price",
    4: "Payment",
    5: "Finish",
  };

  const state = {
    step: 1,
    upload: null,
    quote: null,
    payment: null,
    status: null,
    receipt: null,
    pricing: {
      bw_price_per_page: 500,
      color_price_per_page: 500,
      currency: "TZS",
    },
    mode: "bw",
    paperSize: "a4",
    pageSelection: "all",
    pollTimer: null,
    availabilityTimer: null,
    availability: {
      can_upload: true,
      can_pay: true,
      message: "Kiosk is ready.",
      reason_code: "ok",
    },
    customerConfig: null,
    deviceCode: DEFAULT_DEVICE_CODE,
    paymentMethod: DEFAULT_PAYMENT_METHOD,
    printerCapabilities: {
      color_enabled: true,
      a3_enabled: false,
    },
  };

  const $ = (id) => document.getElementById(id);
  const ui = {
    shell: document.querySelector(".kiosk-shell"),
    siteStrip: $("siteStrip"),
    stepper: $("stepper"),
    progressBar: $("progressBar"),
    stepHint: $("stepHint"),
    qaBadge: $("qaBadge"),
    panels: document.querySelectorAll("[data-step-panel]"),
    kioskBlockBanner: $("kioskBlockBanner"),
    kioskBlockTitle: $("kioskBlockTitle"),
    kioskBlockMessage: $("kioskBlockMessage"),
    brandTitle: $("brandTitle"),
    brandNote: $("brandNote"),
    welcomeTitle: $("welcomeTitle"),
    welcomeLead: $("welcomeLead"),
    trustStrip: $("trustStrip"),
    paymentSectionTitle: $("paymentSectionTitle"),
    paymentSectionLead: $("paymentSectionLead"),
    supportPhone: $("supportPhone"),
    paymentMethodTile: $("paymentMethodTile"),
    paymentMethodLabel: $("paymentMethodLabel"),

    pdfFile: $("pdfFile"),
    uploadBtn: $("uploadBtn"),
    uploadFeedback: $("uploadFeedback"),
    infoFileName: $("infoFileName"),
    infoPageCount: $("infoPageCount"),
    copies: $("copies"),
    modeInputs: document.querySelectorAll('input[name="printMode"]'),
    bwModeOption: $("bwModeOption"),
    colorModeOption: $("colorModeOption"),
    paperSizeField: $("paperSizeField"),
    paperSizeInputs: document.querySelectorAll('input[name="paperSize"]'),
    paperSizeA3Option: $("paperSizeA3Option"),
    pageSelectionInputs: document.querySelectorAll('input[name="pageSelection"]'),
    rangeStartPage: $("rangeStartPage"),
    rangeEndPage: $("rangeEndPage"),
    quickEstimate: $("quickEstimate"),
    toStep3Btn: $("toStep3Btn"),
    sumPages: $("sumPages"),
    sumPageSelection: $("sumPageSelection"),
    sumCopies: $("sumCopies"),
    sumMode: $("sumMode"),
    sumPaperSize: $("sumPaperSize"),
    sumUnitPrice: $("sumUnitPrice"),
    sumTotal: $("sumTotal"),
    backToStep2Btn: $("backToStep2Btn"),
    toStep4Btn: $("toStep4Btn"),
    fullName: $("fullName"),
    msisdn: $("msisdn"),
    backToStep3Btn: $("backToStep3Btn"),
    payBtn: $("payBtn"),
    paymentFeedback: $("paymentFeedback"),
    finishTitle: $("finishTitle"),
    finishMessage: $("finishMessage"),
    finishStatus: $("finishStatus"),
    finishJobId: $("finishJobId"),
    finishRef: $("finishRef"),
    newPrintBtn: $("newPrintBtn"),
  };

  function titleCase(value) {
    const raw = String(value || "").trim();
    if (!raw) return "-";
    return raw.charAt(0).toUpperCase() + raw.slice(1);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function setFeedback(el, tone, message) {
    el.className = `feedback ${tone}`;
    el.textContent = message || "";
  }

  function setStep(step) {
    state.step = step;
    for (const panel of ui.panels) {
      panel.classList.toggle("active", Number(panel.dataset.stepPanel) === step);
    }
    for (const item of ui.stepper.querySelectorAll("li")) {
      const itemStep = Number(item.dataset.step);
      item.classList.toggle("active", itemStep === step);
      item.classList.toggle("done", itemStep < step);
    }
    ui.progressBar.style.width = `${Math.max(1, Math.min(5, step)) * 20}%`;
    ui.stepHint.textContent = `Step ${step} of 5: ${STEP_LABELS[step] || "Progress"}`;
    updateQaBadge();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function updateQaBadge() {
    if (!QA_MODE || !ui.qaBadge) return;
    const viewport = `${window.innerWidth}x${window.innerHeight}`;
    const stepText = `Step ${state.step}: ${STEP_LABELS[state.step] || "-"}`;
    ui.qaBadge.hidden = false;
    ui.qaBadge.textContent = `QA ${viewport} | ${stepText}`;
  }

  function money(value) {
    const currency = state.pricing.currency || "TZS";
    return `${Number(value).toFixed(0)} ${currency}`;
  }

  function unitPriceForMode(mode) {
    return mode === "color"
      ? Number(state.pricing.color_price_per_page || 0)
      : Number(state.pricing.bw_price_per_page || 0);
  }

  function totalCost() {
    if (!state.upload) return 0;
    const copies = Number(ui.copies.value || 1);
    const pages = selectedPagesCount();
    return pages * copies * unitPriceForMode(state.mode);
  }

  function selectedPagesCount() {
    if (!state.upload) return 0;
    const totalPages = Number(state.upload.page_count || 0);
    if (state.pageSelection !== "range") return totalPages;
    const start = Number(ui.rangeStartPage.value || 0);
    const end = Number(ui.rangeEndPage.value || 0);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 1 || end < start || end > totalPages) return 0;
    return (end - start) + 1;
  }

  function pageSelectionLabel() {
    if (state.pageSelection !== "range") return "All pages";
    return `Pages ${ui.rangeStartPage.value} to ${ui.rangeEndPage.value}`;
  }

  function paperSizeLabel() {
    return state.paperSize === "a3" ? "A3" : "A4";
  }

  function resolvePrinterCapabilities(config, deviceCode) {
    const printerCapabilities = config?.printer_capabilities || {};
    const defaults = printerCapabilities.default || {};
    const resolved = {
      color_enabled: Boolean(defaults.color_enabled !== false),
      a3_enabled: Boolean(defaults.a3_enabled),
    };
    const normalizedDeviceCode = String(deviceCode || "").trim();
    if (!normalizedDeviceCode) return resolved;
    const perDeviceFlags = printerCapabilities.devices?.[normalizedDeviceCode];
    if (!perDeviceFlags || typeof perDeviceFlags !== "object") return resolved;

    return {
      color_enabled: Boolean(perDeviceFlags.color_enabled !== false),
      a3_enabled: Boolean(perDeviceFlags.a3_enabled),
    };
  }

  function applyPrinterCapabilities(capabilities) {
    const supportsColor = Boolean(capabilities?.color_enabled !== false);
    const supportsA3 = Boolean(capabilities?.a3_enabled);

    ui.colorModeOption.hidden = !supportsColor;
    if (!supportsColor && state.mode === "color") {
      state.mode = "bw";
    }

    for (const input of ui.modeInputs) {
      if (input.value === "color" && !supportsColor) {
        input.checked = false;
      } else if (input.value === state.mode) {
        input.checked = true;
      }
      const container = input.closest(".mode-option");
      if (container) container.classList.toggle("active", input.checked);
    }

    ui.paperSizeA3Option.hidden = !supportsA3;
    ui.paperSizeField.hidden = !supportsA3;
    if (!supportsA3 && state.paperSize === "a3") {
      state.paperSize = "a4";
    }
    for (const input of ui.paperSizeInputs) {
      if (input.value === "a3" && !supportsA3) {
        input.checked = false;
      } else if (input.value === state.paperSize) {
        input.checked = true;
      }
      const container = input.closest(".mode-option");
      if (container) container.classList.toggle("active", input.checked);
    }

    renderQuickEstimate();
  }

  function renderQuickEstimate() {
    if (!state.upload) {
      ui.quickEstimate.textContent = "Estimated Total: -";
      return;
    }
    const selected = selectedPagesCount();
    const copies = Number(ui.copies.value || 1);
    const modeLabel = state.mode === "color" ? "Color" : "Black & White";
    ui.quickEstimate.textContent = `Estimated Total: ${money(totalCost())} (${selected} page(s) x ${copies} copy/copies, ${modeLabel}, ${paperSizeLabel()})`;
  }

  function syncPageRangeUi() {
    const isRange = state.pageSelection === "range";
    ui.rangeStartPage.disabled = !isRange;
    ui.rangeEndPage.disabled = !isRange;
    for (const input of ui.pageSelectionInputs) {
      const container = input.closest(".mode-option");
      if (container) container.classList.toggle("active", input.checked);
    }
    renderQuickEstimate();
  }

  function renderStep2() {
    ui.infoFileName.textContent = state.upload.file_name;
    ui.infoPageCount.textContent = String(state.upload.page_count);
    ui.copies.value = "1";
    state.mode = "bw";
    state.paperSize = "a4";
    state.pageSelection = "all";
    ui.rangeStartPage.value = "1";
    ui.rangeEndPage.value = String(state.upload.page_count || 1);
    ui.rangeStartPage.max = String(state.upload.page_count || 1);
    ui.rangeEndPage.max = String(state.upload.page_count || 1);
    for (const input of ui.modeInputs) {
      const active = input.value === "bw";
      input.checked = active;
      const container = input.closest(".mode-option");
      if (container) container.classList.toggle("active", active);
    }
    for (const input of ui.paperSizeInputs) {
      const active = input.value === "a4";
      input.checked = active;
      const container = input.closest(".mode-option");
      if (container) container.classList.toggle("active", active);
    }
    for (const input of ui.pageSelectionInputs) {
      input.checked = input.value === "all";
    }
    applyPrinterCapabilities(state.printerCapabilities);
    syncPageRangeUi();
    renderQuickEstimate();
  }

  function renderSummary() {
    const pages = selectedPagesCount();
    const copies = Number(ui.copies.value || 1);
    const modeLabel = state.mode === "color" ? "Color" : "Black & White";
    const unitPrice = unitPriceForMode(state.mode);
    ui.sumPages.textContent = String(pages);
    ui.sumPageSelection.textContent = pageSelectionLabel();
    ui.sumCopies.textContent = String(copies);
    ui.sumMode.textContent = modeLabel;
    ui.sumPaperSize.textContent = paperSizeLabel();
    ui.sumUnitPrice.textContent = money(unitPrice);
    ui.sumTotal.textContent = money(totalCost());
  }

  function parseError(payload, statusCode) {
    if (payload && typeof payload.detail === "string") return payload.detail;
    if (payload && Array.isArray(payload.detail)) return payload.detail.map((x) => x.msg || "Validation error").join("; ");
    return `Request failed (HTTP ${statusCode})`;
  }

  async function callJson(path, options) {
    const response = await fetch(`${API_BASE}${path}`, options);
    let payload = null;
    try {
      payload = await response.json();
    } catch (_err) {
      payload = null;
    }
    if (!response.ok) throw new Error(parseError(payload, response.status));
    return payload;
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    const map = {
      brand_blue: "--brand-blue",
      brand_blue_2: "--brand-blue-2",
      brand_orange: "--brand-orange",
      brand_orange_2: "--brand-orange-2",
      paper: "--paper",
      surface: "--surface",
      ink: "--ink",
      ink_soft: "--ink-soft",
    };
    Object.entries(map).forEach(([key, cssVar]) => {
      const value = String(theme[key] || "").trim();
      if (value) root.style.setProperty(cssVar, value);
    });
  }

  function renderTrustChips(chips) {
    ui.trustStrip.innerHTML = "";
    const list = Array.isArray(chips) ? chips : [];
    const safe = list.length ? list : ["Payment-verified printing", "Auto page detection", "Instant status updates"];
    safe.forEach((text) => {
      const item = document.createElement("span");
      item.className = "trust-pill";
      item.innerHTML = `<i class="trust-icon" aria-hidden="true"></i>${escapeHtml(text)}`;
      ui.trustStrip.appendChild(item);
    });
  }

  function applyAvailability(availability) {
    state.availability = availability || state.availability;
    const canUpload = Boolean(state.availability.can_upload);
    const canPay = Boolean(state.availability.can_pay);
    const message = String(state.availability.message || "Kiosk is temporarily unavailable.");

    ui.uploadBtn.disabled = !canUpload;
    ui.payBtn.disabled = !canPay;

    const shouldShowBlock = !canUpload || !canPay;
    ui.kioskBlockBanner.hidden = !shouldShowBlock;
    if (shouldShowBlock) {
      ui.kioskBlockTitle.textContent = "Kiosk Temporarily Unavailable";
      ui.kioskBlockMessage.textContent = message;
      if (!canUpload) setFeedback(ui.uploadFeedback, "warn", message);
      if (!canPay) setFeedback(ui.paymentFeedback, "warn", message);
    }
  }

  function applyCustomerConfig(payload) {
    state.customerConfig = payload.ui_config || {};
    state.deviceCode = payload.device_code || DEFAULT_DEVICE_CODE;
    state.pricing = {
      bw_price_per_page: Number(payload.pricing?.bw_price_per_page || 500),
      color_price_per_page: Number(payload.pricing?.color_price_per_page || 500),
      currency: String(payload.pricing?.currency || "TZS").toUpperCase(),
    };

    const cfg = state.customerConfig;
    const content = cfg.content || {};
    const theme = cfg.theme || {};
    const flow = cfg.flow || {};
    const resolvedPrinterCapabilities = payload.printer_capabilities || resolvePrinterCapabilities(cfg, state.deviceCode);
    const siteStripText = String(cfg.site_strip_text || "").trim();

    applyTheme(theme);
    if (siteStripText) ui.siteStrip.textContent = siteStripText;
    ui.brandTitle.textContent = content.brand_title || "PrintHub";
    ui.brandNote.textContent = content.brand_note || "Simple, secure, and fast self-service printing kiosk.";
    ui.welcomeTitle.textContent = content.welcome_title || "Karibu Hasnet PrintHub";
    ui.welcomeLead.textContent = content.welcome_lead || "Upload your PDF document and follow simple steps to complete your print.";
    ui.paymentSectionTitle.textContent = content.payment_title || "Payment Details";
    ui.paymentSectionLead.innerHTML = escapeHtml(content.payment_lead || "Enter details and tap Pay to Print.");
    ui.supportPhone.textContent = content.support_phone || "+255 777 019 901";

    renderTrustChips(cfg.chips);

    state.paymentMethod = String(flow.default_payment_method || DEFAULT_PAYMENT_METHOD).toLowerCase();
    ui.paymentMethodLabel.textContent = `${titleCase(state.paymentMethod)} (default)`;
    ui.paymentMethodTile.hidden = Boolean(flow.hide_payment_method !== false);
    ui.shell.classList.toggle("stepper-hidden", flow.show_stepper === false);
    state.printerCapabilities = {
      color_enabled: Boolean(resolvedPrinterCapabilities.color_enabled !== false),
      a3_enabled: Boolean(resolvedPrinterCapabilities.a3_enabled),
    };
    applyPrinterCapabilities(state.printerCapabilities);

    applyAvailability(payload.availability || state.availability);
  }

  async function loadCustomerConfig() {
    const qs = new URLSearchParams();
    if (state.deviceCode) qs.set("device_code", state.deviceCode);
    const payload = await callJson(`/print-jobs/customer-config?${qs.toString()}`, { method: "GET" });
    applyCustomerConfig(payload);
  }

  function splitName(fullName) {
    const cleaned = String(fullName || "").trim().replace(/\s+/g, " ");
    if (!cleaned) return { first: "", last: "" };
    const parts = cleaned.split(" ");
    if (parts.length === 1) return { first: parts[0], last: "Customer" };
    return { first: parts[0], last: parts.slice(1).join(" ") };
  }

  function normalizeMsisdn(value) {
    return String(value || "").trim().replace(/\s+/g, "");
  }

  function validateMsisdnOrThrow(rawMsisdn) {
    const normalized = normalizeMsisdn(rawMsisdn);
    const valid = /^(\+?\d{10,15})$/.test(normalized);
    if (!valid) throw new Error("Please enter a valid mobile number.");
    return normalized;
  }

  async function uploadDocument() {
    if (!state.availability.can_upload) throw new Error(state.availability.message || "Uploading is paused now.");
    const file = ui.pdfFile.files[0];
    if (!file) throw new Error("Please select a PDF file first.");
    setFeedback(ui.uploadFeedback, "warn", "Uploading document...");

    const form = new FormData();
    form.append("file", file, file.name);
    const qs = new URLSearchParams({ device_code: state.deviceCode || DEFAULT_DEVICE_CODE });
    const payload = await callJson(`/print-jobs/upload?${qs.toString()}`, {
      method: "POST",
      body: form,
    });

    state.upload = payload;
    renderStep2();
    setFeedback(ui.uploadFeedback, "ok", "Upload successful.");
    setStep(2);
  }

  async function createQuote() {
    const pages = selectedPagesCount();
    const copies = Number(ui.copies.value || 1);
    const payload = {
      pages,
      copies,
      color: state.mode,
      paper_size: state.paperSize,
      page_selection: state.pageSelection,
      range_start_page: state.pageSelection === "range" ? Number(ui.rangeStartPage.value || 0) : null,
      range_end_page: state.pageSelection === "range" ? Number(ui.rangeEndPage.value || 0) : null,
      device_code: state.deviceCode || DEFAULT_DEVICE_CODE,
      original_file_name: state.upload.file_name,
      upload_id: state.upload.upload_id,
      bw_price_per_page: Number(state.pricing.bw_price_per_page || 0),
      color_price_per_page: Number(state.pricing.color_price_per_page || 0),
      currency: state.pricing.currency,
    };

    return await callJson("/print-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  async function createPayment() {
    if (!state.upload) throw new Error("Upload document first.");
    if (!state.availability.can_pay) throw new Error(state.availability.message || "Payments are paused now.");

    const fullName = ui.fullName.value.trim();
    const msisdn = validateMsisdnOrThrow(ui.msisdn.value);
    if (!fullName) throw new Error("Please enter full name.");

    setFeedback(ui.paymentFeedback, "warn", "Preparing your print order...");
    state.quote = await createQuote();

    const names = splitName(fullName);
    const paymentPayload = {
      print_job_id: state.quote.job_id,
      amount: Number(state.quote.total_cost),
      method: state.paymentMethod || DEFAULT_PAYMENT_METHOD,
      msisdn,
      customer_first_name: names.first,
      customer_last_name: names.last,
      customer_email: "customer@hasnet.local",
    };

    setFeedback(ui.paymentFeedback, "warn", "Sending payment request...");
    const retrySafePayload = await callJson("/payments/retry-safe?reconcile_limit=25", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(paymentPayload),
    });

    state.payment = retrySafePayload.payment;
    setFeedback(ui.paymentFeedback, "ok", "Payment request sent. Please confirm on your phone.");
    showProcessingScreen();
    startStatusPolling();
  }

  function showProcessingScreen() {
    setStep(5);
    ui.finishTitle.textContent = "Payment Initiated";
    ui.finishMessage.textContent = "Please confirm payment on your phone. Printing will start automatically after confirmation.";
    ui.finishStatus.textContent = "Waiting for payment confirmation";
    ui.finishJobId.textContent = state.quote ? state.quote.job_id : "-";
    ui.finishRef.textContent = state.payment ? state.payment.provider_request_id : "-";
  }

  async function fetchStatus() {
    if (!state.quote) return;
    const payload = await callJson(`/print-jobs/${state.quote.job_id}/customer-status`, { method: "GET" });
    state.status = payload;
    ui.finishStatus.textContent = `${payload.stage} / ${payload.payment_status}`;
    ui.finishRef.textContent = payload.provider_request_id || state.payment.provider_request_id || "-";

    if (payload.stage === "completed") {
      stopStatusPolling();
      await finalizeSuccess();
      return;
    }
    if (payload.stage === "payment_failed") {
      stopStatusPolling();
      ui.finishTitle.textContent = "Payment Not Successful";
      ui.finishMessage.textContent = "Your payment was not successful. Please return and try again.";
      return;
    }
    if (payload.stage === "provider_delay_escalated") {
      ui.finishTitle.textContent = "Payment Delay";
      ui.finishMessage.textContent = "Payment confirmation is delayed. Our team is verifying your transaction.";
      return;
    }
    if (payload.stage === "processing" || payload.stage === "payment_confirmed") {
      ui.finishTitle.textContent = "Printing In Progress";
      ui.finishMessage.textContent = "Payment confirmed. Please wait while your document is printing.";
      return;
    }
    ui.finishTitle.textContent = "Waiting for Confirmation";
    ui.finishMessage.textContent = payload.message || "Please wait while payment is being confirmed.";
  }

  async function finalizeSuccess() {
    try {
      state.receipt = await callJson(`/print-jobs/${state.quote.job_id}/customer-receipt`, { method: "GET" });
    } catch (_err) {
      state.receipt = null;
    }

    const content = state.customerConfig?.content || {};
    ui.finishTitle.textContent = content.finish_success_title || "Printing Successful";
    ui.finishMessage.textContent = content.finish_success_message || "Asante! Your document has been printed successfully. Karibu tena.";
    ui.finishStatus.textContent = "Completed";
    if (state.receipt && state.receipt.transaction_reference) {
      ui.finishRef.textContent = state.receipt.transaction_reference;
    }
  }

  function startStatusPolling() {
    stopStatusPolling();
    fetchStatus().catch(() => {});
    state.pollTimer = window.setInterval(() => {
      fetchStatus().catch(() => {});
    }, POLL_INTERVAL_MS);
  }

  function stopStatusPolling() {
    if (state.pollTimer) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function startAvailabilityRefresh() {
    stopAvailabilityRefresh();
    state.availabilityTimer = window.setInterval(() => {
      loadCustomerConfig().catch(() => {});
    }, AVAILABILITY_REFRESH_MS);
  }

  function stopAvailabilityRefresh() {
    if (state.availabilityTimer) {
      window.clearInterval(state.availabilityTimer);
      state.availabilityTimer = null;
    }
  }

  function resetFlow() {
    stopStatusPolling();
    state.upload = null;
    state.quote = null;
    state.payment = null;
    state.status = null;
    state.receipt = null;
    state.mode = "bw";
    state.paperSize = "a4";
    state.pageSelection = "all";
    ui.pdfFile.value = "";
    ui.fullName.value = "";
    ui.msisdn.value = "";
    ui.copies.value = "1";
    ui.quickEstimate.textContent = "Estimated Total: -";
    setFeedback(ui.uploadFeedback, "", "");
    setFeedback(ui.paymentFeedback, "", "");
    applyPrinterCapabilities(state.printerCapabilities);
    setStep(1);
  }

  function bindModeButtons() {
    for (const input of ui.modeInputs) {
      input.addEventListener("change", () => {
        if (!input.checked) return;
        state.mode = input.value;
        for (const peer of ui.modeInputs) {
          const container = peer.closest(".mode-option");
          if (container) container.classList.toggle("active", peer.checked);
        }
        renderQuickEstimate();
      });
    }
  }

  function bindPageSelection() {
    for (const input of ui.pageSelectionInputs) {
      input.addEventListener("change", () => {
        if (!input.checked) return;
        state.pageSelection = input.value;
        syncPageRangeUi();
      });
    }
  }

  function bindPaperSizeButtons() {
    for (const input of ui.paperSizeInputs) {
      input.addEventListener("change", () => {
        if (!input.checked) return;
        state.paperSize = input.value;
        for (const peer of ui.paperSizeInputs) {
          const container = peer.closest(".mode-option");
          if (container) container.classList.toggle("active", peer.checked);
        }
        renderQuickEstimate();
      });
    }
  }

  function bindEvents() {
    ui.uploadBtn.addEventListener("click", async () => {
      ui.uploadBtn.disabled = true;
      try {
        await loadCustomerConfig();
        await uploadDocument();
      } catch (err) {
        setFeedback(ui.uploadFeedback, "bad", err.message || "Upload failed.");
      } finally {
        ui.uploadBtn.disabled = !state.availability.can_upload;
      }
    });

    ui.toStep3Btn.addEventListener("click", () => {
      const copies = Number(ui.copies.value || 0);
      if (copies < 1) {
        setFeedback(ui.uploadFeedback, "bad", "Copies must be at least 1.");
        return;
      }
      if (state.pageSelection === "range") {
        const totalPages = Number(state.upload ? state.upload.page_count : 0);
        const start = Number(ui.rangeStartPage.value || 0);
        const end = Number(ui.rangeEndPage.value || 0);
        if (!Number.isFinite(start) || !Number.isFinite(end) || start < 1 || end < start || end > totalPages) {
          setFeedback(ui.uploadFeedback, "bad", `Custom page range must be between 1 and ${totalPages}.`);
          return;
        }
      }
      renderSummary();
      setStep(3);
    });

    ui.backToStep2Btn.addEventListener("click", () => setStep(2));
    ui.toStep4Btn.addEventListener("click", () => setStep(4));
    ui.backToStep3Btn.addEventListener("click", () => setStep(3));

    ui.payBtn.addEventListener("click", async () => {
      ui.payBtn.disabled = true;
      try {
        await loadCustomerConfig();
        await createPayment();
      } catch (err) {
        setFeedback(ui.paymentFeedback, "bad", err.message || "Payment request failed.");
      } finally {
        ui.payBtn.disabled = !state.availability.can_pay;
      }
    });

    ui.copies.addEventListener("input", renderQuickEstimate);
    ui.rangeStartPage.addEventListener("input", renderQuickEstimate);
    ui.rangeEndPage.addEventListener("input", renderQuickEstimate);
    ui.newPrintBtn.addEventListener("click", resetFlow);
  }

  async function init() {
    bindModeButtons();
    bindPageSelection();
    bindPaperSizeButtons();
    bindEvents();
    if (QA_MODE) {
      updateQaBadge();
      window.addEventListener("resize", updateQaBadge);
    }
    await loadCustomerConfig();
    setStep(1);
    startAvailabilityRefresh();
  }

  init().catch((err) => {
    setFeedback(ui.uploadFeedback, "warn", err.message || "System initialized with defaults.");
    setStep(1);
  });
})();
