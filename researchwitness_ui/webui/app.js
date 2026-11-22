"use strict";

const token = document.querySelector('meta[name="rw-session-token"]').content;
const byId = (id) => document.getElementById(id);
let currentJob = null;
let pollTimer = null;
let generation = 0;

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options,
    headers: { "X-RW-Token": token, ...(options.headers || {}) } });
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.error || "Local request failed");
  }
  return response;
}

function showError(error) {
  byId("error").textContent = error.message;
  byId("error").hidden = false;
}

function clearError() { byId("error").hidden = true; }

function clearReport() {
  byId("report").hidden = true;
  byId("report").removeAttribute("srcdoc");
}

async function presentJob(jobId) {
  const thisGeneration = ++generation;
  clearTimeout(pollTimer);
  clearReport();
  currentJob = jobId;
  byId("results").hidden = false;
  byId("summary").replaceChildren();
  byId("manifest").textContent = "";
  byId("cancel").hidden = true;
  byId("export").hidden = true;
  byId("job-status").textContent = "Loading job…";
  async function update() {
    try {
      const data = await (await api(`/api/jobs/${jobId}`)).json();
      if (thisGeneration !== generation) return;
      const job = data.job;
      byId("job-status").textContent = `${job.filename} · ${job.document_id} · ${job.status}${job.error ? ": " + job.error : ""}`;
      byId("cancel").hidden = job.status !== "queued";
      byId("export").hidden = job.status !== "done";
      byId("summary").replaceChildren();
      for (const [name, count] of Object.entries(job.summary)) {
        const box = document.createElement("div");
        box.className = "metric";
        const value = document.createElement("strong");
        value.textContent = String(count);
        const label = document.createElement("span");
        label.textContent = name.replaceAll("_", " ");
        box.append(value, label);
        byId("summary").append(box);
      }
      if (job.status === "done") {
        byId("manifest").textContent = `Manifest SHA-256: ${job.manifest_sha256}`;
        const html = await (await api(`/api/jobs/${jobId}/report`)).text();
        if (thisGeneration !== generation) return;
        // A sandboxed srcdoc cannot execute scripts or access its parent.
        byId("report").srcdoc = html;
        byId("report").hidden = false;
      }
      if (job.status === "queued" || job.status === "running") {
        pollTimer = setTimeout(update, 700);
      } else {
        await refreshHistory();
      }
    } catch (error) { if (thisGeneration === generation) showError(error); }
  }
  await update();
}

byId("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  const file = byId("paper-file").files[0];
  if (!file) return;
  if (!/\.(n?xml)$/i.test(file.name)) {
    showError(new Error("JATS XML only on this version"));
    return;
  }
  const flags = {};
  document.querySelectorAll('fieldset input[type="checkbox"]').forEach((input) => {
    flags[input.name] = input.checked;
  });
  byId("submit").disabled = true;
  try {
    const data = await (await api("/api/jobs", { method: "POST", body: file,
      headers: { "X-RW-Filename": encodeURIComponent(file.name),
        "X-RW-Document-ID": byId("document-id").value,
        "X-RW-Slices": JSON.stringify(flags), "Content-Type": "application/xml" } })).json();
    await refreshHistory();
    await presentJob(data.job.job_id);
  } catch (error) { showError(error); }
  finally { byId("submit").disabled = false; }
});

byId("cancel").addEventListener("click", async () => {
  clearError();
  try {
    await api(`/api/jobs/${currentJob}/cancel`, { method: "POST" });
    await presentJob(currentJob);
  } catch (error) { showError(error); }
});

byId("export").addEventListener("click", async () => {
  clearError();
  try {
    const blob = await (await api(`/api/jobs/${currentJob}/export`)).blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "researchwitness-jats.zip";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { showError(error); }
});

async function refreshHistory() {
  const data = await (await api("/api/jobs")).json();
  byId("history").replaceChildren();
  if (!data.jobs.length) {
    const empty = document.createElement("li");
    empty.textContent = "No retained jobs.";
    byId("history").append(empty);
  }
  for (const job of data.jobs) {
    const row = document.createElement("li");
    row.className = "history-item";
    const open = document.createElement("button");
    open.type = "button";
    open.textContent = `${job.filename} · ${job.document_id} · ${job.status}`;
    open.addEventListener("click", () => { clearError(); presentJob(job.job_id).catch(showError); });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Delete";
    remove.setAttribute("aria-label", `Delete ${job.filename}, ${job.document_id}`);
    remove.disabled = job.status === "queued" || job.status === "running";
    remove.addEventListener("click", async () => {
      clearError();
      try {
        await api(`/api/jobs/${job.job_id}`, { method: "DELETE" });
        if (currentJob === job.job_id) {
          ++generation;
          clearTimeout(pollTimer);
          clearReport();
          currentJob = null;
          byId("results").hidden = true;
        }
        await refreshHistory();
      } catch (error) { showError(error); }
    });
    row.append(open, remove);
    byId("history").append(row);
  }
}

byId("refresh").addEventListener("click", () => refreshHistory().catch(showError));
refreshHistory().catch(showError);
