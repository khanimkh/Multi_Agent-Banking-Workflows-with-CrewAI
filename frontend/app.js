const API_BASE = window.__API_BASE__ || window.location.origin;
let primaryPollTimer = null;
const defaultButtonText = {};
let toastTimer = null;

async function callApi(path, method = "GET", body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
  return data;
}

function setProcess(value) {
  document.getElementById("processLog").textContent = value;
}

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderMarkdown(markdown) {
  const lines = (markdown || "").split(/\r?\n/);
  let html = "";
  let inList = false;
  let inCode = false;

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (line.startsWith("```")) {
      if (!inCode) {
        html += "<pre><code>";
        inCode = true;
      } else {
        html += "</code></pre>";
        inCode = false;
      }
      continue;
    }

    if (inCode) {
      html += `${escapeHtml(rawLine)}\n`;
      continue;
    }

    if (!line) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      continue;
    }

    if (line.startsWith("### ")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h3>${escapeHtml(line.slice(4))}</h3>`;
      continue;
    }

    if (line.startsWith("## ")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h2>${escapeHtml(line.slice(3))}</h2>`;
      continue;
    }

    if (line.startsWith("# ")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
      continue;
    }

    if (line.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${escapeHtml(line.slice(2))}</li>`;
      continue;
    }

    if (inList) {
      html += "</ul>";
      inList = false;
    }
    html += `<p>${escapeHtml(line)}</p>`;
  }

  if (inList) html += "</ul>";
  if (inCode) html += "</code></pre>";
  return html || "<p>No report output available.</p>";
}

function setResult(value) {
  document.getElementById("reportTitle").textContent = value.title || "Result";
  document.getElementById("reportOutput").innerHTML = renderMarkdown(value.final_markdown || "");
  setProcess(value.process_log || "No process log returned.");
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  toast.classList.toggle("error", isError);

  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
    toast.classList.remove("error");
  }, isError ? 3200 : 2200);
}

function setButtonBusy(buttonId, busy, runningText = "Running...") {
  const btn = document.getElementById(buttonId);
  if (!btn) return;

  if (!defaultButtonText[buttonId]) {
    defaultButtonText[buttonId] = btn.textContent;
  }

  btn.disabled = busy;
  btn.classList.toggle("is-busy", busy);
  btn.textContent = busy ? runningText : defaultButtonText[buttonId];
}

function stopPrimaryPolling() {
  if (primaryPollTimer) {
    clearInterval(primaryPollTimer);
    primaryPollTimer = null;
  }
}

async function pollPrimaryJob(jobId) {
  stopPrimaryPolling();
  primaryPollTimer = setInterval(async () => {
    try {
      const state = await callApi(`/jobs/${jobId}`);
      if (state.process_log) {
        setProcess(state.process_log);
      }
      if (state.status === "completed") {
        stopPrimaryPolling();
        setButtonBusy("runPrimary", false);
        showToast("Primary workflows completed.");
        if (state.result) {
          setResult(state.result);
        }
      }
      if (state.status === "failed") {
        stopPrimaryPolling();
        setButtonBusy("runPrimary", false);
        showToast("Primary workflows failed.", true);
        setProcess(state.error || "Primary job failed.");
      }
    } catch (err) {
      stopPrimaryPolling();
      setButtonBusy("runPrimary", false);
      showToast("Primary workflows polling error.", true);
      setProcess(`Polling error: ${String(err)}`);
    }
  }, 1200);
}

function setRunning(label) {
  document.getElementById("reportTitle").textContent = `${label} running...`;
  document.getElementById("reportOutput").innerHTML = "<p>Waiting for final report...</p>";
  setProcess(`${label} started. Waiting for backend response...`);
}

document.getElementById("runPrimary").onclick = async () => {
  try {
    setButtonBusy("runPrimary", true, "Running Primary...");
    showToast("Primary workflows started.");
    setRunning("Primary workflows");
    const payload = {
      customer_name: document.getElementById("customerName").value,
      customer_goal: document.getElementById("customerGoal").value,
      region: document.getElementById("region").value,
      risk_level: document.getElementById("riskLevel").value,
    };
    const job = await callApi("/jobs/primary", "POST", payload);
    setProcess(`Primary workflows queued (job ${job.job_id}). Starting...`);
    pollPrimaryJob(job.job_id);
  } catch (err) {
    setButtonBusy("runPrimary", false);
    showToast("Failed to start primary workflows.", true);
    setProcess(String(err));
  }
};

document.getElementById("runFlow").onclick = async () => {
  try {
    setButtonBusy("runFlow", true, "Running Flow...");
    showToast("Sales flow started.");
    setRunning("Sales flow");
    const result = await callApi("/run/flow", "POST");
    setResult(result);
    showToast("Sales flow completed.");
  } catch (err) {
    document.getElementById("reportOutput").innerHTML = "<p>Sales flow failed. Check process logs for details.</p>";
    showToast("Sales flow failed.", true);
    setProcess(String(err));
  } finally {
    setButtonBusy("runFlow", false);
  }
};

document.getElementById("runContent").onclick = async () => {
  try {
    setButtonBusy("runContent", true, "Running Content...");
    showToast("Content pipeline started.");
    setRunning("Content pipeline");
    const payload = {
      subject: document.getElementById("subject").value,
      region: document.getElementById("contentRegion").value,
    };
    setResult(await callApi("/run/content", "POST", payload));
    showToast("Content pipeline completed.");
  } catch (err) {
    showToast("Content pipeline failed.", true);
    setProcess(String(err));
  } finally {
    setButtonBusy("runContent", false);
  }
};

document.getElementById("loadReports").onclick = async () => {
  try {
    setButtonBusy("loadReports", true, "Refreshing...");
    const data = await callApi("/reports");
    const list = document.getElementById("reports");
    list.innerHTML = "";
    data.reports.forEach((report) => {
      const li = document.createElement("li");
      li.textContent = report;
      list.appendChild(li);
    });
    showToast("Reports list refreshed.");
    setProcess(`Found ${data.reports.length} report files.`);
  } catch (err) {
    showToast("Failed to load reports.", true);
    setProcess(String(err));
  } finally {
    setButtonBusy("loadReports", false);
  }
};
