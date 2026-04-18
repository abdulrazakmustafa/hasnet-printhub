(function () {
  const API_BASE = `${window.location.origin}/api/v1`;
  const DEFAULT_DEVICE_CODE = "pi-kiosk-001";
  const DEFAULT_PAYMENT_METHOD = "mpesa";
  const POLL_INTERVAL_MS = 5000;
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
    pageSelection: "all",
    pollTimer: null,
  };

  const $ = (id) => document.getElementById(id);
  const ui = {
    stepper: $("stepper"),
    progressBar: $("progressBar"),
    stepHint: $("stepHint"),
    panels: document.querySelectorAll("[data-step-panel]"),
    pdfFile: $("pdfFile"),
    uploadBtn: $("uploadBtn"),
    uploadFeedback: $("uploadFeedback"),
    infoFileName: $("infoFileName"),
    infoPageCount: $("infoPageCount"),
    copies: $("copies"),
    modeInputs: document.querySelectorAll('input[name="printMode"]'),
    pageSelectionInputs: document.querySelectorAll('input[name="pageSelection"]'),
    rangeStartPage: $("rangeStartPage"),
    rangeEndPage: $("rangeEndPage"),
    quickEstimate: $("quickEstimate"),
    toStep3Btn: $("toStep3Btn"),
    sumPages: $("sumPages"),
    sumPageSelection: $("sumPageSelection"),
    sumCopies: $("sumCopies"),
    sumMode: $("sumMode"),
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
    window.scrollTo({ top: 0, behavior: "smooth" });
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
    if (state.pageSelection !== "range") {
      return totalPages;
    }
    const start = Number(ui.rangeStartPage.value || 0);
    const end = Number(ui.rangeEndPage.value || 0);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 1 || end < start || end > totalPages) {
      return 0;
    }
    return (end - start) + 1;
  }

  function pageSelectionLabel() {
    if (state.pageSelection !== "range") {
      return "All pages";
    }
    return `Pages ${ui.rangeStartPage.value} to ${ui.rangeEndPage.value}`;
  }

  function renderQuickEstimate() {
    if (!state.upload) {
      ui.quickEstimate.textContent = "Estimated Total: -";
      return;
    }
    const selected = selectedPagesCount();
    const copies = Number(ui.copies.value || 1);
    const modeLabel = state.mode === "color" ? "Color" : "Black & White";
    ui.quickEstimate.textContent = `Estimated Total: ${money(totalCost())} (${selected} page(s) x ${copies} copy/copies, ${modeLabel})`;
  }

  function syncPageRangeUi() {
    const isRange = state.pageSelection === "range";
    ui.rangeStartPage.disabled = !isRange;
    ui.rangeEndPage.disabled = !isRange;
    for (const input of ui.pageSelectionInputs) {
      const container = input.closest(".mode-option");
      if (container) {
        container.classList.toggle("active", input.checked);
      }
    }
    renderQuickEstimate();
  }

  function renderStep2() {
    ui.infoFileName.textContent = state.upload.file_name;
    ui.infoPageCount.textContent = String(state.upload.page_count);
    ui.copies.value = "1";
    state.mode = "bw";
    state.pageSelection = "all";
    ui.rangeStartPage.value = "1";
    ui.rangeEndPage.value = String(state.upload.page_count || 1);
    ui.rangeStartPage.max = String(state.upload.page_count || 1);
    ui.rangeEndPage.max = String(state.upload.page_count || 1);
    for (const input of ui.modeInputs) {
      const active = input.value === "bw";
      input.checked = active;
      const container = input.closest(".mode-option");
      if (container) {
        container.classList.toggle("active", active);
      }
    }
    for (const input of ui.pageSelectionInputs) {
      input.checked = input.value === "all";
    }
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
    ui.sumUnitPrice.textContent = money(unitPrice);
    ui.sumTotal.textContent = money(totalCost());
  }

  function parseError(payload, statusCode) {
    if (payload && typeof payload.detail === "string") return payload.detail;
    if (payload && Array.isArray(payload.detail)) {
      return payload.detail.map((x) => x.msg || "Validation error").join("; ");
    }
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
    if (!response.ok) {
      throw new Error(parseError(payload, response.status));
    }
    return payload;
  }

  async function loadPricing() {
    try {
      const payload = await callJson("/admin/pricing", { method: "GET" });
      state.pricing = {
        bw_price_per_page: Number(payload.bw_price_per_page || 500),
        color_price_per_page: Number(payload.color_price_per_page || 500),
        currency: String(payload.currency || "TZS").toUpperCase(),
      };
    } catch (_err) {
      state.pricing = {
        bw_price_per_page: 500,
        color_price_per_page: 500,
        currency: "TZS",
      };
    }
  }

  async function uploadDocument() {
    const file = ui.pdfFile.files[0];
    if (!file) {
      throw new Error("Please select a PDF file first.");
    }
    setFeedback(ui.uploadFeedback, "warn", "Uploading document...");

    const form = new FormData();
    form.append("file", file, file.name);
    const payload = await callJson("/print-jobs/upload", {
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
    const unitBw = Number(state.pricing.bw_price_per_page || 0);
    const unitColor = Number(state.pricing.color_price_per_page || 0);

    const payload = {
      pages,
      copies,
      color: state.mode,
      page_selection: state.pageSelection,
      range_start_page: state.pageSelection === "range" ? Number(ui.rangeStartPage.value || 0) : null,
      range_end_page: state.pageSelection === "range" ? Number(ui.rangeEndPage.value || 0) : null,
      device_code: DEFAULT_DEVICE_CODE,
      original_file_name: state.upload.file_name,
      upload_id: state.upload.upload_id,
      bw_price_per_page: unitBw,
      color_price_per_page: unitColor,
      currency: state.pricing.currency,
    };

    return await callJson("/print-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function splitName(fullName) {
    const cleaned = String(fullName || "").trim().replace(/\s+/g, " ");
    if (!cleaned) {
      return { first: "", last: "" };
    }
    const parts = cleaned.split(" ");
    if (parts.length === 1) {
      return { first: parts[0], last: "Customer" };
    }
    return { first: parts[0], last: parts.slice(1).join(" ") };
  }

  function normalizeMsisdn(value) {
    return String(value || "").trim().replace(/\s+/g, "");
  }

  function validateMsisdnOrThrow(rawMsisdn) {
    const normalized = normalizeMsisdn(rawMsisdn);
    const valid = /^(\+?\d{10,15})$/.test(normalized);
    if (!valid) {
      throw new Error("Please enter a valid mobile number.");
    }
    return normalized;
  }

  async function createPayment() {
    if (!state.upload) throw new Error("Upload document first.");
    const fullName = ui.fullName.value.trim();
    const msisdn = validateMsisdnOrThrow(ui.msisdn.value);
    if (!fullName) throw new Error("Please enter full name.");

    setFeedback(ui.paymentFeedback, "warn", "Preparing your print order...");
    state.quote = await createQuote();

    const names = splitName(fullName);
    const paymentPayload = {
      print_job_id: state.quote.job_id,
      amount: Number(state.quote.total_cost),
      method: DEFAULT_PAYMENT_METHOD,
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
    ui.finishTitle.textContent = "Printing Successful";
    ui.finishMessage.textContent = "Asante! Your document has been printed successfully. Karibu tena.";
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

  function resetFlow() {
    stopStatusPolling();
    state.upload = null;
    state.quote = null;
    state.payment = null;
    state.status = null;
    state.receipt = null;
    state.mode = "bw";
    state.pageSelection = "all";
    ui.pdfFile.value = "";
    ui.fullName.value = "";
    ui.msisdn.value = "";
    ui.copies.value = "1";
    ui.quickEstimate.textContent = "Estimated Total: -";
    setFeedback(ui.uploadFeedback, "", "");
    setFeedback(ui.paymentFeedback, "", "");
    setStep(1);
  }

  function bindModeButtons() {
    for (const input of ui.modeInputs) {
      input.addEventListener("change", () => {
        if (!input.checked) return;
        state.mode = input.value;
        for (const peer of ui.modeInputs) {
          const container = peer.closest(".mode-option");
          if (container) {
            container.classList.toggle("active", peer.checked);
          }
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

  function bindEvents() {
    ui.uploadBtn.addEventListener("click", async () => {
      ui.uploadBtn.disabled = true;
      try {
        await uploadDocument();
      } catch (err) {
        setFeedback(ui.uploadFeedback, "bad", err.message || "Upload failed.");
      } finally {
        ui.uploadBtn.disabled = false;
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
        await createPayment();
      } catch (err) {
        setFeedback(ui.paymentFeedback, "bad", err.message || "Payment request failed.");
      } finally {
        ui.payBtn.disabled = false;
      }
    });

    ui.copies.addEventListener("input", renderQuickEstimate);
    ui.rangeStartPage.addEventListener("input", renderQuickEstimate);
    ui.rangeEndPage.addEventListener("input", renderQuickEstimate);

    ui.newPrintBtn.addEventListener("click", resetFlow);
  }

  async function init() {
    await loadPricing();
    bindModeButtons();
    bindPageSelection();
    bindEvents();
    setStep(1);
  }

  init().catch(() => {
    setFeedback(ui.uploadFeedback, "warn", "System initialized with default pricing.");
  });
})();
