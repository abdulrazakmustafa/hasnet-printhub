(function () {
  const API_BASE = `${window.location.origin}/api/v1`;
  const DEFAULT_DEVICE_CODE = "pi-kiosk-001";
  const POLL_INTERVAL_MS = 5000;

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
    pollTimer: null,
  };

  const $ = (id) => document.getElementById(id);
  const ui = {
    stepper: $("stepper"),
    panels: document.querySelectorAll("[data-step-panel]"),
    pdfFile: $("pdfFile"),
    uploadBtn: $("uploadBtn"),
    uploadFeedback: $("uploadFeedback"),
    infoFileName: $("infoFileName"),
    infoPageCount: $("infoPageCount"),
    copies: $("copies"),
    modeSelector: $("modeSelector"),
    toStep3Btn: $("toStep3Btn"),
    sumPages: $("sumPages"),
    sumCopies: $("sumCopies"),
    sumMode: $("sumMode"),
    sumUnitPrice: $("sumUnitPrice"),
    sumTotal: $("sumTotal"),
    backToStep2Btn: $("backToStep2Btn"),
    toStep4Btn: $("toStep4Btn"),
    fullName: $("fullName"),
    msisdn: $("msisdn"),
    method: $("method"),
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
      item.classList.toggle("active", Number(item.dataset.step) === step);
    }
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
    const pages = Number(state.upload.page_count || 0);
    return pages * copies * unitPriceForMode(state.mode);
  }

  function renderStep2() {
    ui.infoFileName.textContent = state.upload.file_name;
    ui.infoPageCount.textContent = String(state.upload.page_count);
    ui.copies.value = "1";
    state.mode = "bw";
    for (const btn of ui.modeSelector.querySelectorAll("button")) {
      btn.classList.toggle("active", btn.dataset.mode === "bw");
    }
  }

  function renderSummary() {
    const pages = Number(state.upload.page_count || 0);
    const copies = Number(ui.copies.value || 1);
    const modeLabel = state.mode === "color" ? "Color" : "Black & White";
    const unitPrice = unitPriceForMode(state.mode);
    ui.sumPages.textContent = String(pages);
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
    const pages = Number(state.upload.page_count || 0);
    const copies = Number(ui.copies.value || 1);
    const unitBw = Number(state.pricing.bw_price_per_page || 0);
    const unitColor = Number(state.pricing.color_price_per_page || 0);

    const payload = {
      pages,
      copies,
      color: state.mode,
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

  async function createPayment() {
    if (!state.upload) throw new Error("Upload document first.");
    const fullName = ui.fullName.value.trim();
    const msisdn = ui.msisdn.value.trim();
    if (!fullName) throw new Error("Please enter full name.");
    if (!msisdn) throw new Error("Please enter mobile number.");

    setFeedback(ui.paymentFeedback, "warn", "Preparing your print order...");
    state.quote = await createQuote();

    const names = splitName(fullName);
    const paymentPayload = {
      print_job_id: state.quote.job_id,
      amount: Number(state.quote.total_cost),
      method: ui.method.value,
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
    ui.pdfFile.value = "";
    ui.fullName.value = "";
    ui.msisdn.value = "";
    ui.method.value = "mpesa";
    ui.copies.value = "1";
    setFeedback(ui.uploadFeedback, "", "");
    setFeedback(ui.paymentFeedback, "", "");
    setStep(1);
  }

  function bindModeButtons() {
    for (const btn of ui.modeSelector.querySelectorAll("button")) {
      btn.addEventListener("click", () => {
        state.mode = btn.dataset.mode;
        for (const peer of ui.modeSelector.querySelectorAll("button")) {
          peer.classList.toggle("active", peer.dataset.mode === state.mode);
        }
      });
    }
  }

  function bindEvents() {
    ui.uploadBtn.addEventListener("click", async () => {
      try {
        await uploadDocument();
      } catch (err) {
        setFeedback(ui.uploadFeedback, "bad", err.message || "Upload failed.");
      }
    });

    ui.toStep3Btn.addEventListener("click", () => {
      const copies = Number(ui.copies.value || 0);
      if (copies < 1) {
        setFeedback(ui.uploadFeedback, "bad", "Copies must be at least 1.");
        return;
      }
      renderSummary();
      setStep(3);
    });

    ui.backToStep2Btn.addEventListener("click", () => setStep(2));
    ui.toStep4Btn.addEventListener("click", () => setStep(4));
    ui.backToStep3Btn.addEventListener("click", () => setStep(3));

    ui.payBtn.addEventListener("click", async () => {
      try {
        await createPayment();
      } catch (err) {
        setFeedback(ui.paymentFeedback, "bad", err.message || "Payment request failed.");
      }
    });

    ui.newPrintBtn.addEventListener("click", resetFlow);
  }

  async function init() {
    await loadPricing();
    bindModeButtons();
    bindEvents();
    setStep(1);
  }

  init().catch(() => {
    setFeedback(ui.uploadFeedback, "warn", "System initialized with default pricing.");
  });
})();
