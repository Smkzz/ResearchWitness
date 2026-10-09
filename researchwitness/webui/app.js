"use strict";

const token = document.querySelector('meta[name="rw-session-token"]').content;
const fileInput = document.getElementById("paper-file");
const runButton = document.getElementById("run-button");
const selectedFile = document.getElementById("selected-file");
const progressPanel = document.getElementById("progress-panel");
const resultsPanel = document.getElementById("results-panel");
const findingsRoot = document.getElementById("findings");
let currentJob = null;
let polling = false;

function apiHeaders(extra = {}) {
  return { "X-RW-Token": token, ...extra };
}

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options,
    headers: apiHeaders(options.headers || {}) });
  let payload;
  if (response.headers.get("Content-Type")?.startsWith("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.blob();
  }
  if (!response.ok) throw new Error(payload?.error || "LOCAL_OPERATION_FAILED");
  return { response, payload };
}

function setText(node, value) { node.textContent = value == null ? "" : String(value); }

function makeElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) setText(node, text);
  return node;
}

function showError(message) {
  const box = document.getElementById("error-note");
  const labels = {
    FILE_TOO_LARGE: "This file is over the 32 MiB limit.",
    UNSUPPORTED_FILE_FORMAT: "Choose a .txt, .md, .markdown, .xml, .nxml, or .pdf file.",
    EMPTY_FILE: "The selected file is empty.",
    ACTIVE_RUNS_MUST_FINISH_OR_CANCEL: "Cancel active runs before deleting local run data.",
    LOCAL_HISTORY_LIMIT_REACHED_DELETE_OLD_RUNS: "The local history is full. Delete old runs before starting another analysis.",
    INPUT_UNSUPPORTED_OR_INVALID: "This input could not be screened. Check that it is a supported, readable file.",
    REPORT_NOT_READY: "The report is not ready yet.",
    RUN_STILL_ACTIVE: "This run is still active.",
    LOCAL_DATA_REQUIRES_MANUAL_REVIEW: "The local run store contains data this application cannot identify safely. It has not been changed; review that folder manually before continuing.",
    LOCAL_SOURCE_CHANGED: "The saved source file changed after upload. This run was stopped to preserve its source binding.",
    LOCAL_SOURCE_UNAVAILABLE: "The saved source file is unavailable. The report cannot be replayed from this run.",
  };
  setText(box, labels[message] || `The local operation stopped (${message}). Your source contents were not added to an error message.`);
  box.hidden = false;
  box.focus();
}

function clearError() {
  const box = document.getElementById("error-note");
  box.hidden = true;
  box.textContent = "";
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  setText(selectedFile, file ? `${file.name} · ${formatBytes(file.size)}` : "No file selected.");
  runButton.disabled = !file;
  clearError();
});

const dropZone = document.getElementById("drop-zone");
dropZone.addEventListener("dragover", (event) => {
  event.preventDefault(); dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", (event) => {
  event.preventDefault(); dropZone.classList.remove("dragging");
  const file = event.dataTransfer?.files?.[0];
  if (!file) return;
  const transfer = new DataTransfer(); transfer.items.add(file); fileInput.files = transfer.files;
  fileInput.dispatchEvent(new Event("change", { bubbles: true }));
});

runButton.addEventListener("click", () => submitFile(false));

async function submitFile(force) {
  clearError();
  const file = fileInput.files?.[0];
  if (!file) return;
  const extension = file.name.split(".").pop()?.toLowerCase();
  const allowed = new Set(["txt", "md", "markdown", "xml", "nxml", "pdf"]);
  if (!allowed.has(extension)) { showError("UNSUPPORTED_FILE_FORMAT"); return; }
  if (!file.size) { showError("EMPTY_FILE"); return; }
  if (file.size > 32 * 1024 * 1024) { showError("FILE_TOO_LARGE"); return; }
  const identifier = encodeURIComponent(document.getElementById("paper-id").value.trim());
  const version = encodeURIComponent(document.getElementById("paper-version").value.trim());
  const headers = {
    "Content-Type": "application/octet-stream",
    "X-RW-Name": encodeURIComponent(file.name),
    "X-RW-Identifier": identifier,
    "X-RW-Version": version,
  };
  try {
    runButton.disabled = true;
    const { payload } = await api("/api/jobs", { method: "POST", headers, body: file });
    currentJob = payload.job;
    document.getElementById("duplicate-note").hidden = !payload.duplicate;
    if (payload.duplicate) setText(document.getElementById("duplicate-note"), "This exact file and configuration already has a local result. ResearchWitness opened the cached run; use Replay this exact input to run it again.");
    await presentJob(currentJob.job_id, payload.duplicate);
  } catch (error) {
    showError(error.message);
  } finally {
    runButton.disabled = !fileInput.files?.length;
  }
}

async function presentJob(jobId, duplicate = false) {
  progressPanel.hidden = false;
  resultsPanel.hidden = true;
  if (duplicate) progressPanel.hidden = true;
  polling = true;
  try {
    while (polling) {
      const { payload } = await api(`/api/jobs/${jobId}`);
      currentJob = payload.job;
      updateProgress(currentJob);
      if (!["QUEUED", "ANALYZING", "CANCELLING"].includes(currentJob.status)) break;
      await new Promise((resolve) => setTimeout(resolve, 450));
    }
  } catch (error) {
    polling = false;
    progressPanel.hidden = true;
    showError(error.message);
    return;
  }
  polling = false;
  progressPanel.hidden = true;
  resultsPanel.hidden = false;
  await refreshHistory();
  if (currentJob.status === "COMPLETED") await loadReport(jobId, duplicate);
  else renderTerminal(currentJob);
}

function updateProgress(job) {
  setText(document.getElementById("progress-stage"), job.stage_label || job.stage);
  const cancelling = job.status === "CANCELLING";
  document.getElementById("cancel-button").disabled = cancelling;
  if (cancelling) setText(document.getElementById("progress-detail"), "Cancellation is cooperative. The active bounded parser/check stops at its next safe boundary.");
}

document.getElementById("cancel-button").addEventListener("click", async () => {
  if (!currentJob) return;
  try {
    const { payload } = await api(`/api/jobs/${currentJob.job_id}/cancel`, { method: "POST" });
    currentJob = payload.job; updateProgress(currentJob);
  } catch (error) { showError(error.message); }
});

async function loadReport(jobId, duplicate = false) {
  clearError();
  try {
    const { payload } = await api(`/api/reports/${jobId}`);
    currentJob = payload.job;
    renderReport(payload, duplicate);
  } catch (error) { showError(error.message); }
}

function renderTerminal(job) {
  setText(document.getElementById("result-status"), job.status === "CANCELLED" ? "Run cancelled" : `Run ${job.status.toLowerCase()}`);
  const summary = document.getElementById("result-summary");
  summary.replaceChildren(makeElement("p", "result-banner", job.error_code ? `The run stopped (${job.error_code}). The same input is still saved locally for retry.` : job.stage));
  document.getElementById("export-button").hidden = true;
  document.getElementById("replay-button").hidden = true;
  document.getElementById("retry-button").hidden = !["FAILED", "CANCELLED", "INTERRUPTED"].includes(job.status);
  document.getElementById("full-report-details").hidden = true;
  document.getElementById("replay-help").hidden = true;
  document.getElementById("duplicate-note").hidden = true;
  findingsRoot.replaceChildren();
}

function renderReport(data, duplicate) {
  const job = data.job;
  const decisions = {
    CANDIDATES_FOUND: "Review candidates found",
    CANDIDATES_FOUND_IN_INCOMPLETE_SCAN: "Candidates found; scan incomplete",
    NO_CANDIDATES_IN_SUPPORTED_SCAN: "No candidates in supported checks",
    SCAN_INCOMPLETE_NO_CANDIDATES: "No candidates found; scan incomplete",
    EXTRACTION_UNAVAILABLE_OR_EMPTY: "No usable text extracted",
  };
  setText(document.getElementById("result-status"), decisions[job.decision] || job.status);
  const summary = document.getElementById("result-summary");
  summary.replaceChildren();
  const caution = makeElement("div", "result-banner");
  const cautionTitle = makeElement("strong", "", "Screening result, not a verified paper error");
  caution.append(cautionTitle, document.createTextNode(data.meaning));
  summary.append(caution);

  const metrics = makeElement("div", "summary-grid");
  const items = [
    [job.candidate_count ?? 0, "candidate relationships needing review"],
    [job.scope_question_count ?? 0, "possible scope differences"],
    [job.extraction_status || "unknown", `extraction status · ${job.extraction_format || "format"}`],
  ];
  for (const [value, label] of items) {
    const metric = makeElement("div", "metric");
    metric.append(makeElement("strong", "", value), makeElement("span", "", label)); metrics.append(metric);
  }
  summary.append(metrics);

  const identity = makeElement("div", "subsection");
  identity.append(makeElement("h3", "", "Source and version"));
  const identityList = makeElement("ul", "plain-list");
  [
    `File: ${job.original_name}`,
    `Identifier: ${job.identifier}`,
    `Version label: ${job.source_version}`,
    `Capture status: ${data.capture_status}; the source and version were not authenticated.`,
    `Source SHA-256: ${data.source_hash}`,
    `Extracted text SHA-256: ${data.extracted_text_hash}`,
    `OCR performed: ${data.ocr_performed ? "yes" : "no"}`,
  ].forEach((text) => identityList.append(makeElement("li", "", text)));
  identity.append(identityList); summary.append(identity);

  const coverage = makeElement("div", "subsection");
  coverage.append(makeElement("h3", "", "What was checked"));
  if (job.checks_attempted?.length) {
    const list = makeElement("ul", "plain-list");
    job.checks_attempted.forEach((item) => list.append(makeElement("li", "", friendlyCheck(item))));
    coverage.append(list);
  } else coverage.append(makeElement("p", "muted", "No supported detector ran for this input."));
  coverage.append(makeElement("h3", "", "Coverage and skipped checks"));
  const coverageList = makeElement("div", "coverage-list");
  for (const item of job.detector_eligibility || []) {
    const row = makeElement("div", "coverage-row");
    row.append(makeElement("code", "", item.detector_id || "check"));
    row.append(makeElement("span", "coverage-status", `${item.status || "UNKNOWN"} · ${item.checked_operands ?? 0} checked`));
    row.append(makeElement("span", "coverage-reason", (item.reasons || []).join("; ") || "No additional skip reason recorded."));
    coverageList.append(row);
  }
  coverage.append(coverageList);
  if (job.unsupported_checks?.length) {
    const list = makeElement("ul", "plain-list");
    job.unsupported_checks.forEach((item) => list.append(makeElement("li", "", item)));
    coverage.append(list);
  }
  if (data.extraction_warnings?.length) {
    coverage.append(makeElement("h3", "", "Input warnings"));
    const list = makeElement("ul", "plain-list");
    data.extraction_warnings.forEach((item) => list.append(makeElement("li", "", item)));
    coverage.append(list);
  }
  summary.append(coverage);

  document.getElementById("export-button").hidden = false;
  document.getElementById("replay-button").hidden = false;
  document.getElementById("retry-button").hidden = true;
  document.getElementById("full-report-details").hidden = false;
  document.getElementById("replay-help").hidden = false;
  const frame = document.getElementById("full-report");
  frame.srcdoc = data.full_report_html;
  renderFindings(data.findings || [], data.scope_questions || [],
                 data.findings_total ?? (data.findings || []).length,
                 data.scope_questions_total ?? (data.scope_questions || []).length);
  document.getElementById("duplicate-note").hidden = !duplicate;
}

function friendlyCheck(value) {
  const labels = {
    explicit_count_marker_scan: "Explicit n/N count-marker scan",
    explicit_exclusion_flow_arithmetic_screen: "Explicit sample-flow relationship screen",
    markdown_table_percentage_recomputation: "Markdown table percentage recomputation",
    jats_table_percentage_recomputation: "JATS table percentage recomputation",
    jats_cell_ratio_percentage_recomputation: "JATS cell ratio and percentage checks",
    jats_sd_se_n_recomputation: "JATS standard-deviation, standard-error, and n checks",
    jats_sample_flow_arithmetic: "JATS sample-flow arithmetic",
    prisma_synthesis_flow: "JATS review-flow arithmetic",
    jats_unadjusted_2x2_odds_ratio: "JATS unadjusted 2×2 odds ratio",
  };
  return labels[value] || value;
}

function renderFindings(findings, scopeQuestions, findingsTotal, scopeQuestionsTotal) {
  findingsRoot.replaceChildren();
  const heading = makeElement("h3", "subsection", "Findings to inspect");
  findingsRoot.append(heading);
  if (findings.length < findingsTotal) {
    findingsRoot.append(makeElement("p", "muted", `Showing ${findings.length} of ${findingsTotal} candidate relationships here. Open the complete evidence report for the full list.`));
  }
  if (!findings.length) findingsRoot.append(makeElement("p", "muted", "No candidate was emitted by the supported checks. This is not evidence that the paper is correct."));
  for (const item of findings) {
    const card = makeElement("article", "finding-card");
    card.append(makeElement("h4", "", `${item.type || "Candidate"} · ${item.status || "REVIEW"}`));
    const operands = [];
    if (item.numerator_exact !== undefined) operands.push(`Numerator ${item.numerator_exact}`);
    if (item.denominator_exact !== undefined) operands.push(`denominator ${item.denominator_exact}`);
    if (item.reported_percent !== undefined) operands.push(`printed ${item.reported_percent}%`);
    if (item.recomputed_percent !== undefined) operands.push(`recomputed ${item.recomputed_percent}%`);
    if (operands.length) card.append(makeElement("p", "", operands.join(" · ")));
    if (item.denominator_exact !== undefined) {
      const provenance = item.denominator_provenance || {};
      const selected = provenance.selected_denominator || {};
      const origin = selected.structural_source || (item.scope_label ? "explicit table-column heading" : "source excerpt");
      const detail = selected.source_anchor?.quote || item.source_anchors?.[0]?.quote;
      card.append(makeElement("p", "", `Denominator origin: ${origin}${detail ? ` · “${detail}”` : ""}.`));
      const rejected = provenance.rejected_competing_denominators || [];
      if (rejected.length) {
        const list = makeElement("ul", "plain-list");
        rejected.slice(0, 4).forEach((candidate) => {
          const quote = candidate.source_anchor?.quote;
          const reasons = (candidate.rejection_reasons || []).join("; ") || "lower semantic scope";
          list.append(makeElement("li", "", `Other denominator ${candidate.value_exact || candidate.raw_value || "unresolved"} rejected: ${reasons}${quote ? ` · “${quote}”` : ""}`));
        });
        card.append(makeElement("p", "muted", "Competing denominator evidence"), list);
      } else if (item._possible_alternate_denominators?.length) {
        card.append(makeElement("p", "muted", `Other detected denominators: ${item._possible_alternate_denominators.join(", ")}. Their applicability was not resolved.`));
      }
    }
    if (item.table || item.table_id || item.cell_id) {
      card.append(makeElement("p", "muted", `Location: ${[item.table_id, item.cell_id, item.table].filter(Boolean).join(" · ")}`));
    }
    if (item.interpretation) card.append(makeElement("p", "", item.interpretation));
    if (item.required_review) card.append(makeElement("p", "muted", `Review: ${item.required_review}`));
    for (const anchor of (item.source_anchors || []).slice(0, 12)) {
      const location = [];
      if (anchor.element_path) location.push(anchor.element_path);
      if (Number.isFinite(anchor.line_number)) location.push(`line ${anchor.line_number}`);
      if (Number.isFinite(anchor.start_byte)) location.push(`byte ${anchor.start_byte}`);
      const quote = makeElement("blockquote", "evidence-quote", `${anchor.quote || anchor.text || "Source anchor"}${location.length ? ` · ${location.join(" · ")}` : ""}`);
      card.append(quote);
    }
    findingsRoot.append(card);
  }
  if (scopeQuestions.length) {
    findingsRoot.append(makeElement("h3", "subsection", "Questions about scope"));
    if (scopeQuestions.length < scopeQuestionsTotal) {
      findingsRoot.append(makeElement("p", "muted", `Showing ${scopeQuestions.length} of ${scopeQuestionsTotal} possible scope differences here. Open the complete evidence report for the full list.`));
    }
    for (const item of scopeQuestions) {
      const card = makeElement("article", "finding-card");
      card.append(makeElement("h4", "", item.type || "Possible scope difference"));
      const scopeValues = [];
      if (item.numerator_exact !== undefined) scopeValues.push(`Numerator ${item.numerator_exact}`);
      if (item.column_denominator_exact !== undefined) scopeValues.push(`column denominator ${item.column_denominator_exact}`);
      if (item.compatible_alternate_denominators_exact?.length) {
        scopeValues.push(`compatible row-specific denominator ${item.compatible_alternate_denominators_exact.join(", ")}`);
      }
      if (item.reported_percent !== undefined) scopeValues.push(`printed ${item.reported_percent}%`);
      if (scopeValues.length) card.append(makeElement("p", "", scopeValues.join(" · ")));
      if (item.scope_label || item.table) {
        card.append(makeElement("p", "muted", `Location: ${[item.table, item.scope_label].filter(Boolean).join(" · ")}`));
      }
      if (item.interpretation) card.append(makeElement("p", "", item.interpretation));
      if (item.required_review) card.append(makeElement("p", "muted", `Review: ${item.required_review}`));
      for (const anchor of (item.source_anchors || []).slice(0, 12)) {
        const location = [];
        if (anchor.element_path) location.push(anchor.element_path);
        if (Number.isFinite(anchor.line_number)) location.push(`line ${anchor.line_number}`);
        if (Number.isFinite(anchor.start_byte)) location.push(`byte ${anchor.start_byte}`);
        card.append(makeElement("blockquote", "evidence-quote", `${anchor.quote || "Source anchor"}${location.length ? ` · ${location.join(" · ")}` : ""}`));
      }
      findingsRoot.append(card);
    }
  }
}

document.getElementById("export-button").addEventListener("click", async () => {
  if (!currentJob) return;
  try {
    const { payload } = await api(`/api/exports/${currentJob.job_id}.zip`);
    const url = URL.createObjectURL(payload);
    const link = document.createElement("a");
    link.href = url; link.download = `researchwitness-report-${currentJob.job_id.slice(0, 8)}.zip`;
    document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  } catch (error) { showError(error.message); }
});

document.getElementById("replay-button").addEventListener("click", async () => {
  if (!currentJob) return;
  try {
    const { payload } = await api(`/api/jobs/${currentJob.job_id}/retry`, { method: "POST" });
    currentJob = payload.job; await presentJob(currentJob.job_id, false);
  } catch (error) { showError(error.message); }
});

document.getElementById("retry-button").addEventListener("click", async () => {
  if (!currentJob) return;
  try {
    const { payload } = await api(`/api/jobs/${currentJob.job_id}/retry`, { method: "POST" });
    currentJob = payload.job; await presentJob(currentJob.job_id, false);
  } catch (error) { showError(error.message); }
});

async function refreshHistory() {
  const root = document.getElementById("history-list");
  try {
    const { payload } = await api("/api/jobs");
    root.replaceChildren();
    if (!payload.jobs.length) root.append(makeElement("p", "muted", "No saved runs."));
    for (const job of payload.jobs) {
      const row = makeElement("div", "history-item");
      const button = makeElement("button", "", `${job.original_name} · ${job.status.toLowerCase()}`);
      button.type = "button";
      button.addEventListener("click", async () => {
        currentJob = job;
        if (["QUEUED", "ANALYZING", "CANCELLING"].includes(job.status)) {
          await presentJob(job.job_id);
          resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
        resultsPanel.hidden = false;
        if (job.status === "COMPLETED") await loadReport(job.job_id);
        else renderTerminal(job);
        resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      row.append(button, makeElement("span", "", job.created_at_utc)); root.append(row);
    }
    const warning = document.getElementById("store-warning");
    if (payload.warning) { setText(warning, `Local history needs review: ${payload.warning}`); warning.hidden = false; }
  } catch (error) { showError(error.message); }
}

document.getElementById("delete-data").addEventListener("click", async () => {
  if (!window.confirm("Delete all ResearchWitness local run data and saved paper copies from this application? Exported packages and system backups are not deleted.")) return;
  try {
    await api("/api/data", { method: "DELETE" });
    resultsPanel.hidden = true; progressPanel.hidden = true; currentJob = null;
    fileInput.value = "";
    selectedFile.textContent = "No file selected.";
    runButton.disabled = true;
    document.getElementById("duplicate-note").hidden = true;
    document.getElementById("history-list").replaceChildren(makeElement("p", "muted", "No saved runs."));
    clearError();
  } catch (error) { showError(error.message); }
});

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

refreshHistory().then(async () => {
  try {
    const { payload } = await api("/api/jobs");
    const active = payload.jobs.find((job) => ["QUEUED", "ANALYZING", "CANCELLING"].includes(job.status));
    if (active && !polling) {
      currentJob = active;
      await presentJob(active.job_id);
    }
  } catch (error) { showError(error.message); }
}).catch((error) => showError(error.message));
