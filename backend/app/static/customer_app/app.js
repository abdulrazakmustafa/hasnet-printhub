(function () {
  const state = {
    upload: null,
    quote: null,
    payment: null,
    status: null,
    receipt: null,
    pollTimer: null,
  };

  const $ = (id) => document.getElementById(id);

  const els = {
    apiBaseUrl: $("apiBaseUrl"),
    pdfFile: $("pdfFile"),
    pages: $("pages"),
    copies: $("copies"),
    color: $("color"),
    currency: $("currency"),
    bwPrice: $("bwPrice"),
    colorPrice: $("colorPrice"),
    deviceCode: $("deviceCode"),
    method: $("method"),
    msisdn: $("msisdn"),
    firstName: $("firstName"),
    lastName: $("lastName"),
    email: $("email"),
    uploadBtn: $("uploadBtn"),
    quoteBtn: $("quoteBtn"),
    payBtn: $("payBtn"),
    retrySafeBtn: $("retrySafeBtn"),
    statusBtn: $("statusBtn"),
    pollBtn: $("pollBtn"),
    receiptBtn: $("receiptBtn"),
    uploadSummary: $("uploadSummary"),
    quoteSummary: $("quoteSummary"),
    paymentSummary: $("paymentSummary"),
    statusSummary: $("statusSummary"),
    receiptSummary: $("receiptSummary"),
    timelineList: $("timelineList"),
    logPanel: $("logPanel"),
  };

  function nowIso() {
    return new Date().toISOString().replace("T", " ").replace("Z", "");
  }

  function log(message, payload) {
    const line = `[${nowIso()}] ${message}`;
    const extra = payload ? `\n${JSON.stringify(payload, null, 2)}\n` : "\n";
    els.logPanel.textContent = line + extra + els.logPanel.textContent;
  }

  function setSummary(el, tone, lines) {
    el.className = `summary ${tone}`;
    el.innerHTML = lines.map((line) => `<div>${line}</div>`).join("");
  }

  function parseApiError(response, body) {
    if (!body) {
      return `HTTP ${response.status}`;
    }
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      return body.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    }
    return `HTTP ${response.status}`;
  }

  async function callApi(path, options) {
    const base = (els.apiBaseUrl.value || "").trim().replace(/\/+$/, "");
    const url = `${base}${path}`;
    const response = await fetch(url, options);
    let body = null;
    try {
      body = await response.json();
    } catch (_err) {
      body = null;
    }
    if (!response.ok) {
      throw new Error(parseApiError(response, body));
    }
    return body;
  }

  function quotePayload() {
    if (!state.upload) {
      throw new Error("Upload a PDF first.");
    }
    const file = els.pdfFile.files[0];
    return {
      pages: Number(els.pages.value),
      copies: Number(els.copies.value),
      color: els.color.value,
      device_code: els.deviceCode.value.trim(),
      original_file_name: file ? file.name : "document.pdf",
      upload_id: state.upload.upload_id,
      bw_price_per_page: Number(els.bwPrice.value),
      color_price_per_page: Number(els.colorPrice.value),
      currency: els.currency.value.trim().toUpperCase(),
    };
  }

  function paymentPayload() {
    if (!state.quote) {
      throw new Error("Create quote first.");
    }
    return {
      print_job_id: state.quote.job_id,
      amount: Number(state.quote.total_cost),
      method: els.method.value,
      msisdn: els.msisdn.value.trim(),
      customer_first_name: els.firstName.value.trim(),
      customer_last_name: els.lastName.value.trim(),
      customer_email: els.email.value.trim(),
    };
  }

  async function uploadPdf() {
    const file = els.pdfFile.files[0];
    if (!file) {
      throw new Error("Choose a PDF file first.");
    }
    const form = new FormData();
    form.append("file", file, file.name);
    const upload = await callApi("/print-jobs/upload", {
      method: "POST",
      body: form,
    });
    state.upload = upload;
    setSummary(els.uploadSummary, "ok", [
      `<strong>upload_id:</strong> ${upload.upload_id}`,
      `<strong>file:</strong> ${upload.file_name}`,
      `<strong>size:</strong> ${upload.file_size_bytes} bytes`,
      `<strong>sha256:</strong> ${upload.sha256}`,
    ]);
    log("Upload successful.", upload);
  }

  async function createQuote() {
    const payload = quotePayload();
    const quote = await callApi("/print-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.quote = quote;
    setSummary(els.quoteSummary, "ok", [
      `<strong>job_id:</strong> ${quote.job_id}`,
      `<strong>status:</strong> ${quote.status}`,
      `<strong>total:</strong> ${quote.total_cost} ${quote.currency}`,
    ]);
    log("Quote created.", { request: payload, response: quote });
  }

  async function createPayment(useRetrySafe) {
    const payload = paymentPayload();
    const path = useRetrySafe
      ? "/payments/retry-safe?reconcile_limit=25"
      : "/payments/create";
    const response = await callApi(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const payment = useRetrySafe ? response.payment : response;
    state.payment = payment;

    const detailLine = useRetrySafe
      ? `<strong>decision:</strong> ${response.decision} (reconcile_synced=${response.reconcile_synced})`
      : "<strong>decision:</strong> standard payment create";

    setSummary(els.paymentSummary, "ok", [
      detailLine,
      `<strong>payment_id:</strong> ${payment.payment_id}`,
      `<strong>status:</strong> ${payment.status}`,
      `<strong>provider_ref:</strong> ${payment.provider_request_id}`,
    ]);
    log("Payment create successful.", { request: payload, response });
  }

  function renderTimeline(events) {
    els.timelineList.innerHTML = "";
    for (const event of events || []) {
      const li = document.createElement("li");
      li.classList.add(`state-${event.state}`);
      const atText = event.at ? ` at ${event.at}` : "";
      li.innerHTML = `<strong>${event.label}</strong> - ${event.state}${atText}<br>${event.detail || ""}`;
      els.timelineList.appendChild(li);
    }
  }

  function pickStatusTone(stage) {
    if (stage === "failed") return "bad";
    if (stage === "provider_delay_escalated" || stage === "payment_pending") return "warn";
    return "ok";
  }

  async function fetchStatus() {
    if (!state.quote) {
      throw new Error("Create quote first.");
    }
    const statusPayload = await callApi(`/print-jobs/${state.quote.job_id}/customer-status`, {
      method: "GET",
    });
    state.status = statusPayload;

    setSummary(els.statusSummary, pickStatusTone(statusPayload.stage), [
      `<strong>stage:</strong> ${statusPayload.stage}`,
      `<strong>message:</strong> ${statusPayload.message}`,
      `<strong>next action:</strong> ${statusPayload.next_action}`,
      `<strong>job status:</strong> ${statusPayload.job_status}`,
      `<strong>payment status:</strong> ${statusPayload.payment_status}`,
    ]);
    renderTimeline(statusPayload.timeline || []);
    log("Customer status fetched.", statusPayload);
  }

  async function fetchReceipt() {
    if (!state.quote) {
      throw new Error("Create quote first.");
    }
    const receipt = await callApi(`/print-jobs/${state.quote.job_id}/customer-receipt`, {
      method: "GET",
    });
    state.receipt = receipt;

    const headline = receipt.headline || "Receipt";
    setSummary(els.receiptSummary, "ok", [
      `<strong>headline:</strong> ${headline}`,
      `<strong>stage:</strong> ${receipt.stage}`,
      `<strong>payment status:</strong> ${receipt.payment_status}`,
      `<strong>issued at:</strong> ${receipt.issued_at}`,
    ]);
    log("Customer receipt fetched.", receipt);
  }

  function startStopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      els.pollBtn.textContent = "Start Auto Poll";
      log("Auto-poll stopped.");
      return;
    }

    if (!state.quote) {
      setSummary(els.statusSummary, "warn", ["Create quote first, then start polling."]);
      return;
    }

    state.pollTimer = setInterval(async () => {
      try {
        await fetchStatus();
      } catch (err) {
        log(`Auto-poll error: ${err.message}`);
      }
    }, 5000);
    els.pollBtn.textContent = "Stop Auto Poll";
    log("Auto-poll started (5s).");
  }

  async function runAction(action, onErrorSummary) {
    try {
      await action();
    } catch (err) {
      const message = err && err.message ? err.message : "Unexpected error";
      onErrorSummary(message);
      log(`Error: ${message}`);
    }
  }

  function initDefaults() {
    els.apiBaseUrl.value = `${window.location.origin}/api/v1`;
    els.logPanel.textContent = "";
  }

  function bindEvents() {
    els.uploadBtn.addEventListener("click", () =>
      runAction(uploadPdf, (message) => setSummary(els.uploadSummary, "bad", [message]))
    );

    els.quoteBtn.addEventListener("click", () =>
      runAction(createQuote, (message) => setSummary(els.quoteSummary, "bad", [message]))
    );

    els.payBtn.addEventListener("click", () =>
      runAction(() => createPayment(false), (message) => setSummary(els.paymentSummary, "bad", [message]))
    );

    els.retrySafeBtn.addEventListener("click", () =>
      runAction(() => createPayment(true), (message) => setSummary(els.paymentSummary, "bad", [message]))
    );

    els.statusBtn.addEventListener("click", () =>
      runAction(fetchStatus, (message) => setSummary(els.statusSummary, "bad", [message]))
    );

    els.receiptBtn.addEventListener("click", () =>
      runAction(fetchReceipt, (message) => setSummary(els.receiptSummary, "bad", [message]))
    );

    els.pollBtn.addEventListener("click", startStopPolling);
  }

  initDefaults();
  bindEvents();
  log("Customer app ready.");
})();
