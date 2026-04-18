(function () {
  const API_BASE = `${window.location.origin}/api/v1`;
  const ui = {
    bw: document.getElementById("bw"),
    color: document.getElementById("color"),
    currency: document.getElementById("currency"),
    saveBtn: document.getElementById("saveBtn"),
    reloadBtn: document.getElementById("reloadBtn"),
    status: document.getElementById("status"),
    preview: document.getElementById("preview"),
  };

  function setStatus(message, tone) {
    ui.status.textContent = message || "";
    ui.status.style.color = tone === "bad" ? "#ef476f" : tone === "ok" ? "#89d96a" : "#ffd166";
  }

  function preview(payload) {
    ui.preview.textContent = `BW: ${payload.bw_price_per_page} ${payload.currency} | Color: ${payload.color_price_per_page} ${payload.currency}`;
  }

  async function call(path, options) {
    const response = await fetch(`${API_BASE}${path}`, options);
    let body = null;
    try {
      body = await response.json();
    } catch (_err) {
      body = null;
    }
    if (!response.ok) {
      const detail = body && body.detail ? body.detail : `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  async function loadPricing() {
    setStatus("Loading pricing...", "warn");
    try {
      const payload = await call("/admin/pricing", { method: "GET" });
      ui.bw.value = payload.bw_price_per_page;
      ui.color.value = payload.color_price_per_page;
      ui.currency.value = payload.currency;
      preview(payload);
      setStatus("Pricing loaded.", "ok");
    } catch (err) {
      setStatus(`Load failed: ${err.message}`, "bad");
    }
  }

  async function savePricing() {
    const payload = {
      bw_price_per_page: Number(ui.bw.value || 0),
      color_price_per_page: Number(ui.color.value || 0),
      currency: (ui.currency.value || "").trim().toUpperCase(),
    };
    setStatus("Saving pricing...", "warn");
    try {
      const saved = await call("/admin/pricing", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      preview(saved);
      setStatus("Pricing saved.", "ok");
    } catch (err) {
      setStatus(`Save failed: ${err.message}`, "bad");
    }
  }

  ui.saveBtn.addEventListener("click", savePricing);
  ui.reloadBtn.addEventListener("click", loadPricing);
  loadPricing();
})();
