"""Static dashboard HTML for the FastAPI app."""
from __future__ import annotations


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Effective Boolean Filter</title>
  <style nonce="__CSP_NONCE__">
    :root {
      color-scheme: light;
      --bg: #f7f8f5;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #5f6c7b;
      --line: #d7ddd6;
      --teal: #14746f;
      --teal-dark: #0e5551;
      --blue: #1d4ed8;
      --amber: #b7791f;
      --red: #b42318;
      --soft-red: #fff1f0;
      --soft-amber: #fff8e6;
      --soft-green: #ecfdf5;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-width: 320px;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--sans);
      font-size: 15px;
      line-height: 1.45;
      letter-spacing: 0;
    }

    header {
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      max-width: 1180px;
      margin: 0 auto;
      padding: 14px 20px;
    }

    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
    }

    main {
      display: grid;
      grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
      gap: 16px;
      max-width: 1180px;
      margin: 0 auto;
      padding: 16px 20px 24px;
    }

    .left-stack {
      display: grid;
      align-content: start;
      gap: 16px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }

    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 44px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }

    .panel-title {
      margin: 0;
      font-size: 14px;
      font-weight: 700;
    }

    form {
      display: grid;
      gap: 12px;
      padding: 12px;
    }

    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      font: inherit;
      min-height: 38px;
      padding: 8px 10px;
    }

    textarea {
      min-height: 128px;
      resize: vertical;
    }

    .row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 132px;
      gap: 10px;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .presets {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 12px 4px;
    }

    .presets-label {
      width: 100%;
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    button {
      min-height: 38px;
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 8px 12px;
      background: #ffffff;
      color: var(--ink);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }

    button.primary {
      background: var(--teal);
      color: #ffffff;
    }

    button.primary:hover { background: var(--teal-dark); }

    button.secondary {
      border-color: var(--line);
    }

    button.preset {
      min-height: 32px;
      padding: 6px 10px;
      border-color: var(--line);
      background: #ffffff;
      color: var(--ink);
      font-size: 13px;
      font-weight: 600;
    }

    button.preset:hover { background: var(--soft-green); }

    button.icon {
      min-height: 28px;
      padding: 4px 8px;
      border-color: var(--line);
      font-size: 12px;
      font-weight: 600;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.65;
    }

    .score-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    .score-table th, .score-table td {
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }

    .score-table th {
      width: 35%;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }

    .score-bar {
      position: relative;
      width: 100%;
      height: 8px;
      margin-top: 4px;
      border-radius: 4px;
      background: var(--line);
      overflow: hidden;
    }

    .score-bar-fill {
      position: absolute;
      top: 0;
      left: 0;
      height: 100%;
      background: var(--teal);
    }

    .score-value {
      font-family: var(--mono);
      font-size: 12px;
      color: var(--ink);
    }

    .score-reasons {
      margin: 4px 0 0;
      padding: 0 0 0 16px;
      list-style: disc;
      color: var(--muted);
      font-size: 12px;
    }

    .json-toolbar {
      display: flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 6px;
    }

    .copy-feedback {
      font-size: 12px;
      color: var(--muted);
    }

    .copy-feedback.ok { color: var(--teal); }
    .copy-feedback.err { color: var(--red); }

    .outputer-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: end;
      margin-bottom: 8px;
    }

    .outputer-style-label {
      flex: 0 0 auto;
      width: 140px;
    }

    .outputer-status {
      flex: 1 1 auto;
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .outputer-status.ok { color: var(--teal); }
    .outputer-status.err { color: var(--red); }
    .outputer-status.cached { color: var(--blue); }

    .advisory-source-help {
      margin: 0;
      font-size: 12px;
    }

    .inputer-status {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 8px;
      margin: 0;
      padding: 0;
    }

    .inputer-status > div {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: #ffffff;
    }

    .inputer-status dt {
      margin: 0;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .inputer-status dd {
      margin: 2px 0 0;
      font-family: var(--mono);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .ledger-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 8px;
      align-items: end;
    }

    .ledger-strip > div {
      min-height: 54px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: #ffffff;
    }

    .ledger-strip span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .ledger-strip strong {
      display: block;
      margin-top: 2px;
      font-family: var(--mono);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .ledger-status {
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .ledger-status.ok { color: var(--teal); }
    .ledger-status.err { color: var(--red); }

    .outputer-output {
      display: grid;
      gap: 10px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
    }

    .outputer-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      font-family: var(--mono);
      font-size: 11px;
      color: var(--muted);
    }

    .outputer-section h4 {
      margin: 0 0 4px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--muted);
    }

    .outputer-section p,
    .outputer-section li {
      margin: 0;
      overflow-wrap: anywhere;
    }

    .outputer-section ol,
    .outputer-section ul {
      margin: 0;
      padding-left: 18px;
    }

    .advisory-body {
      display: grid;
      gap: 12px;
      padding: 12px;
    }

    .advisory-body textarea {
      min-height: 86px;
    }

    .advisory-selected {
      display: grid;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #ffffff;
      font-size: 13px;
    }

    .advisory-selected .code {
      color: var(--ink);
    }

    .status-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border-bottom: 1px solid var(--line);
    }

    .metric {
      min-height: 76px;
      padding: 12px;
      border-right: 1px solid var(--line);
    }

    .metric:last-child { border-right: 0; }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .metric strong {
      display: block;
      margin-top: 6px;
      overflow-wrap: anywhere;
      font-size: 20px;
    }

    .content-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
      gap: 16px;
      padding: 16px;
    }

    .section {
      min-width: 0;
      margin-bottom: 16px;
    }

    .section h3 {
      margin: 0 0 8px;
      font-size: 13px;
      text-transform: uppercase;
      color: var(--muted);
    }

    .list {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .item {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #ffffff;
    }

    .item.error { background: var(--soft-red); border-color: #ffc9c4; }
    .item.warning { background: var(--soft-amber); border-color: #f4d58d; }
    .item.ok { background: var(--soft-green); border-color: #b7ebd0; }

    .code {
      font-family: var(--mono);
      font-size: 12px;
      color: var(--blue);
      overflow-wrap: anywhere;
    }

    .muted { color: var(--muted); }

    pre {
      max-height: 320px;
      overflow: auto;
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #111827;
      color: #e5e7eb;
      padding: 12px;
      font-family: var(--mono);
      font-size: 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .empty {
      padding: 18px;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 6px;
      background: #ffffff;
    }

    @media (max-width: 900px) {
      main, .content-grid {
        grid-template-columns: 1fr;
      }

      .status-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .metric:nth-child(2) { border-right: 0; }
      .metric:nth-child(-n + 2) { border-bottom: 1px solid var(--line); }
    }

    @media (max-width: 520px) {
      .topbar, main {
        padding-left: 12px;
        padding-right: 12px;
      }

      .row, .status-grid {
        grid-template-columns: 1fr;
      }

      .metric {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }

      .metric:last-child { border-bottom: 0; }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <h1>Effective Boolean Filter</h1>
      <span class="muted" id="health">checking</span>
    </div>
  </header>
  <main>
    <div class="left-stack">
      <section class="panel">
        <div class="panel-header">
          <h2 class="panel-title">Input</h2>
        </div>
        <form id="eval-form">
          <label>
            Claim
            <input id="claim" name="claim" required value="X is true">
          </label>
          <label>
            Argument
            <textarea id="argument" name="argument" required>There is no evidence against X, therefore X is true</textarea>
          </label>
          <div class="row">
            <label>
              Context
              <input id="context" name="context" value="scientific argument">
            </label>
            <label>
              Strictness
              <select id="strictness" name="strictness">
                <option value="low">low</option>
                <option value="medium" selected>medium</option>
                <option value="high">high</option>
              </select>
            </label>
          </div>
          <div class="actions">
            <button class="primary" type="submit" id="submit">Evaluate</button>
          </div>
        </form>
        <div class="presets" role="group" aria-label="Sample presets">
          <p class="presets-label">Try a sample</p>
          <button class="preset" type="button" data-preset="clean_double_negation">Clean double negation</button>
          <button class="preset" type="button" data-preset="epistemic_shift">Epistemic shift</button>
          <button class="preset" type="button" data-preset="scope_shift">Scope shift</button>
          <button class="preset" type="button" data-preset="contained_contradiction">Contained contradiction</button>
        </div>
      </section>

      <section class="panel" id="advisory-panel">
        <div class="panel-header">
          <h2 class="panel-title">Azatoth/Nyahlothep</h2>
          <span class="muted" id="advisory-status">ready</span>
        </div>
        <div class="advisory-body">
          <label>
            Seed statement
            <textarea id="advisory-seed">X is true</textarea>
          </label>
          <div class="row">
            <label>
              Context
              <input id="advisory-context" value="scientific argument">
            </label>
            <label>
              Count
              <input id="advisory-count" type="number" min="1" max="20" value="8">
            </label>
          </div>
          <div class="row">
            <label>
              Advisory strictness
              <select id="advisory-strictness">
                <option value="low">low</option>
                <option value="medium" selected>medium</option>
                <option value="high">high</option>
              </select>
            </label>
            <label>
              Azatoth source
              <select id="advisory-source" aria-describedby="advisory-source-help">
                <option value="deterministic" selected>deterministic</option>
                <option value="inputer">inputer (LLM, fake)</option>
              </select>
            </label>
          </div>
          <p class="advisory-source-help muted" id="advisory-source-help">
            Inputer uses the deterministic fake LLM client by default; no real provider is called in this build.
          </p>
          <section class="section" id="provider-status-section" aria-live="polite">
            <h3>Provider status</h3>
            <div class="ledger-strip">
              <div><span>Provider</span><strong id="provider-name">checking</strong></div>
              <div><span>Model</span><strong id="provider-model">-</strong></div>
              <div><span>Configured</span><strong id="provider-configured">-</strong></div>
              <button class="secondary" type="button" id="check-provider">
                Check provider
              </button>
              <span class="ledger-status" id="provider-status-message" role="status">
                Checking provider config.
              </span>
            </div>
          </section>
          <div class="actions">
            <button class="primary" type="button" id="run-wrapper">Run wrapper</button>
            <button class="secondary" type="button" id="load-selected" disabled>Load selected</button>
          </div>
          <section class="section" id="inputer-status-section" hidden aria-live="polite">
            <h3>Azatoth inputer status</h3>
            <dl class="inputer-status" id="inputer-status">
              <div><dt>Provider</dt><dd id="inputer-provider">-</dd></div>
              <div><dt>Model</dt><dd id="inputer-model">-</dd></div>
              <div><dt>Cached</dt><dd id="inputer-cached">-</dd></div>
              <div><dt>Pool size</dt><dd id="inputer-pool">-</dd></div>
              <div><dt>Valid</dt><dd id="inputer-valid">-</dd></div>
              <div><dt>Deduped</dt><dd id="inputer-deduped">-</dd></div>
              <div><dt>Returned</dt><dd id="inputer-returned">-</dd></div>
            </dl>
          </section>
          <section class="section">
            <h3>Candidate ranking</h3>
            <ol class="list" id="advisory-ranking"><li class="empty">No wrapper run yet.</li></ol>
          </section>
          <section class="section">
            <h3>Trace + gates</h3>
            <ul class="list" id="advisory-trace-gates"><li class="empty">No trace yet.</li></ul>
          </section>
          <section class="section" id="ledger-section" aria-live="polite">
            <h3>Ledger replay</h3>
            <div class="ledger-strip">
              <div><span>Entry</span><strong id="ledger-entry">disabled</strong></div>
              <div><span>Sequence</span><strong id="ledger-sequence">-</strong></div>
              <div><span>Hash</span><strong id="ledger-hash">-</strong></div>
              <button class="secondary" type="button" id="replay-ledger" disabled>
                Replay verify
              </button>
              <span class="ledger-status" id="ledger-replay-status" role="status">
                Ledger off.
              </span>
            </div>
          </section>
          <section class="section">
            <h3>Selected candidate</h3>
            <div id="selected-candidate" class="empty">No selection yet.</div>
          </section>
          <section class="section" id="outputer-section" aria-live="polite">
            <h3>Nyahlothep narration</h3>
            <div class="outputer-controls">
              <label class="outputer-style-label">
                Style
                <select id="outputer-style">
                  <option value="brief" selected>brief</option>
                  <option value="technical">technical</option>
                  <option value="replication">replication</option>
                </select>
              </label>
              <button class="primary" type="button" id="generate-output" disabled>
                Generate narration
              </button>
              <span class="outputer-status muted" id="outputer-status" role="status">
                Run the wrapper first.
              </span>
            </div>
            <div id="outputer-result" class="empty">No narration yet.</div>
          </section>
        </div>
      </section>
    </div>

    <section class="panel" aria-live="polite">
      <div class="status-grid">
        <div class="metric"><span>Polarity</span><strong id="polarity">-</strong></div>
        <div class="metric"><span>Recommendation</span><strong id="recommendation">-</strong></div>
        <div class="metric"><span>Effectiveness</span><strong id="effectiveness">-</strong></div>
        <div class="metric"><span>Bogusness</span><strong id="bogusness">-</strong></div>
      </div>
      <div class="content-grid">
        <div>
          <section class="section">
            <h3>Score breakdown</h3>
            <div id="score-vector"><div class="empty">No report yet.</div></div>
          </section>
          <section class="section">
            <h3>Issues</h3>
            <ul class="list" id="issues"><li class="empty">No report yet.</li></ul>
          </section>
          <section class="section">
            <h3>Trace</h3>
            <ul class="list" id="trace"><li class="empty">No report yet.</li></ul>
          </section>
        </div>
        <div>
          <section class="section">
            <h3>Probes</h3>
            <ul class="list" id="probes"><li class="empty">No report yet.</li></ul>
          </section>
          <section class="section">
            <h3>JSON</h3>
            <div class="json-toolbar">
              <button class="icon" type="button" id="copy-json" aria-label="Copy report JSON to clipboard">Copy JSON</button>
              <span class="copy-feedback" id="copy-feedback" role="status" aria-live="polite"></span>
            </div>
            <pre id="json">{}</pre>
          </section>
        </div>
      </div>
    </section>
  </main>
  <script nonce="__CSP_NONCE__">
    const form = document.querySelector("#eval-form");
    const submit = document.querySelector("#submit");
    const health = document.querySelector("#health");
    const copyBtn = document.querySelector("#copy-json");
    const copyFeedback = document.querySelector("#copy-feedback");
    const advisory = {
      seed: document.querySelector("#advisory-seed"),
      context: document.querySelector("#advisory-context"),
      count: document.querySelector("#advisory-count"),
      strictness: document.querySelector("#advisory-strictness"),
      source: document.querySelector("#advisory-source"),
      inputerSection: document.querySelector("#inputer-status-section"),
      inputerFields: {
        provider: document.querySelector("#inputer-provider"),
        model: document.querySelector("#inputer-model"),
        cached: document.querySelector("#inputer-cached"),
        pool: document.querySelector("#inputer-pool"),
        valid: document.querySelector("#inputer-valid"),
        deduped: document.querySelector("#inputer-deduped"),
        returned: document.querySelector("#inputer-returned")
      },
      run: document.querySelector("#run-wrapper"),
      load: document.querySelector("#load-selected"),
      status: document.querySelector("#advisory-status"),
      providerFields: {
        name: document.querySelector("#provider-name"),
        model: document.querySelector("#provider-model"),
        configured: document.querySelector("#provider-configured"),
        check: document.querySelector("#check-provider"),
        message: document.querySelector("#provider-status-message")
      },
      ranking: document.querySelector("#advisory-ranking"),
      traceGates: document.querySelector("#advisory-trace-gates"),
      ledgerEntry: document.querySelector("#ledger-entry"),
      ledgerSequence: document.querySelector("#ledger-sequence"),
      ledgerHash: document.querySelector("#ledger-hash"),
      ledgerReplay: document.querySelector("#replay-ledger"),
      ledgerStatus: document.querySelector("#ledger-replay-status"),
      selected: document.querySelector("#selected-candidate")
    };
    const outputer = {
      style: document.querySelector("#outputer-style"),
      generate: document.querySelector("#generate-output"),
      status: document.querySelector("#outputer-status"),
      result: document.querySelector("#outputer-result")
    };
    let latestAdvisoryRun = null;
    const fields = {
      polarity: document.querySelector("#polarity"),
      recommendation: document.querySelector("#recommendation"),
      effectiveness: document.querySelector("#effectiveness"),
      bogusness: document.querySelector("#bogusness"),
      scoreVector: document.querySelector("#score-vector"),
      issues: document.querySelector("#issues"),
      trace: document.querySelector("#trace"),
      probes: document.querySelector("#probes"),
      json: document.querySelector("#json")
    };

    const PRESETS = {
      clean_double_negation: {
        claim: "P",
        argument: "It is not the case that not P. Therefore P.",
        context: "logic",
        strictness: "medium"
      },
      epistemic_shift: {
        claim: "X is true",
        argument: "There is no evidence against X, therefore X is true.",
        context: "scientific argument",
        strictness: "medium"
      },
      scope_shift: {
        claim: "It works in production",
        argument: "It works in simulation. Therefore it works in production.",
        context: "engineering",
        strictness: "medium"
      },
      contained_contradiction: {
        claim: "The model is useful in restricted context B",
        argument: "The model failed in context A. The model works in context B. Therefore the model is useful in restricted context B.",
        context: "ml evaluation",
        strictness: "medium"
      }
    };

    const SCORE_FIELDS = [
      ["negation_consistency", "Negation consistency"],
      ["scope_preservation", "Scope preservation"],
      ["definition_stability", "Definition stability"],
      ["context_fit", "Context fit"],
      ["contradiction_containment", "Contradiction containment"],
      ["reactive_performance", "Reactive performance"],
      ["testability", "Testability"],
      ["implementation_relevance", "Implementation relevance"]
    ];

    function setList(node, rows, render, emptyText) {
      node.replaceChildren();
      if (!rows || rows.length === 0) {
        const empty = document.createElement("li");
        empty.className = "empty";
        empty.textContent = emptyText;
        node.appendChild(empty);
        return;
      }
      rows.forEach(row => node.appendChild(render(row)));
    }

    function item(className, top, body) {
      const li = document.createElement("li");
      li.className = `item ${className || ""}`.trim();
      const code = document.createElement("div");
      code.className = "code";
      code.textContent = top;
      const text = document.createElement("div");
      text.textContent = body;
      li.append(code, text);
      return li;
    }

    function renderScoreVector(scoreVector) {
      fields.scoreVector.replaceChildren();
      if (!scoreVector) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "No score vector available.";
        fields.scoreVector.appendChild(empty);
        return;
      }
      const reasons = scoreVector.reasons || {};
      const table = document.createElement("table");
      table.className = "score-table";
      SCORE_FIELDS.forEach(([key, label]) => {
        const value = Number(scoreVector[key] ?? 0);
        const tr = document.createElement("tr");

        const th = document.createElement("th");
        th.scope = "row";
        th.textContent = label;

        const td = document.createElement("td");
        const valueRow = document.createElement("div");
        valueRow.className = "score-value";
        valueRow.textContent = value.toFixed(2);
        td.appendChild(valueRow);

        const bar = document.createElement("div");
        bar.className = "score-bar";
        bar.setAttribute("role", "progressbar");
        bar.setAttribute("aria-valuemin", "0");
        bar.setAttribute("aria-valuemax", "1");
        bar.setAttribute("aria-valuenow", value.toFixed(2));
        const fill = document.createElement("div");
        fill.className = "score-bar-fill";
        const pct = Math.max(0, Math.min(100, value * 100));
        fill.style.width = pct + "%";
        bar.appendChild(fill);
        td.appendChild(bar);

        const fieldReasons = reasons[key];
        if (Array.isArray(fieldReasons) && fieldReasons.length > 0) {
          const ul = document.createElement("ul");
          ul.className = "score-reasons";
          fieldReasons.forEach(text => {
            const li = document.createElement("li");
            li.textContent = text;
            ul.appendChild(li);
          });
          td.appendChild(ul);
        }

        tr.append(th, td);
        table.appendChild(tr);
      });
      fields.scoreVector.appendChild(table);
    }

    function renderReport(report) {
      fields.polarity.textContent = report.effective_polarity;
      fields.recommendation.textContent = report.recommendation;
      fields.effectiveness.textContent = Number(report.effectiveness_score).toFixed(3);
      fields.bogusness.textContent = Number(report.bogusness_score).toFixed(3);
      fields.json.textContent = JSON.stringify(report, null, 2);

      renderScoreVector(report.score_vector);

      setList(
        fields.issues,
        report.issues,
        issue => item(issue.severity, issue.code, issue.message),
        "No detected issues."
      );

      setList(
        fields.trace,
        report.trace,
        step => item(step.tracked ? "ok" : "warning", step.transformation_type, step.reason),
        "No trace emitted."
      );

      setList(
        fields.probes,
        report.probes,
        probe => item("", probe.type, probe.question),
        "No probes emitted."
      );
    }

    function setAdvisoryStatus(message) {
      advisory.status.textContent = message;
    }

    function setProviderStatusMessage(message, state) {
      advisory.providerFields.message.textContent = message;
      advisory.providerFields.message.className = "ledger-status" + (state ? " " + state : "");
    }

    function renderProviderStatus(payload) {
      advisory.providerFields.name.textContent = String(payload.provider || "?");
      advisory.providerFields.model.textContent = String(payload.model || "-");
      advisory.providerFields.configured.textContent = payload.configured ? "yes" : "no";
      if (payload.configured) {
        setProviderStatusMessage(
          payload.live ? "Live provider configured." : "Deterministic fake provider.",
          "ok"
        );
      } else {
        const errors = Array.isArray(payload.errors) ? payload.errors.join("; ") : "not configured";
        setProviderStatusMessage(errors, "err");
      }
    }

    async function checkProviderStatus() {
      advisory.providerFields.check.disabled = true;
      setProviderStatusMessage("Checking provider config.", "");
      try {
        const response = await fetch("/advisory/provider/status");
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || response.statusText);
        }
        renderProviderStatus(payload);
      } catch (error) {
        advisory.providerFields.name.textContent = "?";
        advisory.providerFields.model.textContent = "-";
        advisory.providerFields.configured.textContent = "no";
        setProviderStatusMessage(
          "Provider status failed: " + (error && error.message ? error.message : "unknown error"),
          "err"
        );
      } finally {
        advisory.providerFields.check.disabled = false;
      }
    }

    function renderSelectedCandidate(candidate, selection) {
      advisory.selected.replaceChildren();
      advisory.selected.className = "advisory-selected";
      const rows = [
        ["Candidate", candidate.candidate_id],
        ["Template", candidate.template],
        ["Claim", candidate.claim],
        ["Argument", candidate.argument],
        ["Context", candidate.context || "(none)"],
        ["Reason", selection.rank_reason]
      ];
      rows.forEach(([label, value]) => {
        const row = document.createElement("div");
        const top = document.createElement("div");
        top.className = "code";
        top.textContent = label;
        const body = document.createElement("div");
        body.textContent = value;
        row.append(top, body);
        advisory.selected.appendChild(row);
      });
    }

    function renderAdvisoryTraceGates(run) {
      const rows = [];
      if (run.trace && Array.isArray(run.trace.stages)) {
        run.trace.stages.forEach(stage => {
          rows.push({
            state: stage.status === "pass" ? "ok" : "warning",
            label: stage.name,
            detail: stage.evidence_hash
          });
        });
      }
      if (run.gates && run.gates.promotion) {
        rows.push({
          state: run.gates.promotion.status === "pass" ? "ok" : "warning",
          label: "promotion_gate",
          detail: run.gates.promotion.evidence_hash
        });
      }
      if (run.gates && run.gates.reality) {
        rows.push({
          state: run.gates.reality.status === "pass" ? "ok" : "warning",
          label: "reality_gate",
          detail: run.gates.reality.evidence_hash
        });
      }
      setList(
        advisory.traceGates,
        rows,
        row => item(row.state, row.label, row.detail),
        "No trace yet."
      );
    }

    function renderAdvisory(run) {
      latestAdvisoryRun = run;
      const selection = run.nyahlothep_selection;
      const candidate = run.replication_recipe.selected_candidate;
      setList(
        advisory.ranking,
        selection.ranking,
        row => item(
          row.error_count ? "warning" : "ok",
          "#" + row.rank + " " + row.candidate_id,
          row.template + " | " + row.recommendation + " | " +
            Number(row.effectiveness_score).toFixed(3) + " | " +
            row.rank_reason
        ),
        "No candidates ranked."
      );
      renderAdvisoryTraceGates(run);
      renderLedgerStatus(run);
      renderSelectedCandidate(candidate, selection);
      renderInputerStatus(run);
      advisory.load.disabled = false;
      setAdvisoryStatus("selected");
      renderReport(run.selected_report);
      // a fresh wrapper run invalidates any prior narration; the user must
      // click Generate again to call the outputer for this report.
      clearOutputerOutput("No narration yet for this run.");
      setOutputerEnabled();
    }

    function renderInputerStatus(run) {
      const inputer = run && run.azatoth_inputer;
      if (!inputer) {
        advisory.inputerSection.hidden = true;
        return;
      }
      advisory.inputerSection.hidden = false;
      // every value goes through textContent — the inputer payload is
      // derived from user-supplied seed/context text, so it must stay
      // text-only.
      advisory.inputerFields.provider.textContent = String(inputer.provider || "?");
      advisory.inputerFields.model.textContent = String(inputer.model || "?");
      advisory.inputerFields.cached.textContent = inputer.cached ? "yes" : "no";
      advisory.inputerFields.pool.textContent = String(inputer.pool_size);
      advisory.inputerFields.valid.textContent = String(inputer.valid_count);
      advisory.inputerFields.deduped.textContent = String(inputer.deduped_count);
      advisory.inputerFields.returned.textContent = String(
        (run.azatoth_candidates && run.azatoth_candidates.length) ||
          (run.replication_recipe && run.replication_recipe.selected_candidate ? "1" : "0")
      );
    }

    function setLedgerStatus(message, state) {
      advisory.ledgerStatus.textContent = message;
      advisory.ledgerStatus.className = "ledger-status" + (state ? " " + state : "");
    }

    function resetLedgerStatus(message) {
      advisory.ledgerEntry.textContent = "disabled";
      advisory.ledgerSequence.textContent = "-";
      advisory.ledgerHash.textContent = "-";
      advisory.ledgerReplay.disabled = true;
      setLedgerStatus(message || "Ledger off.", "");
    }

    function renderLedgerStatus(run) {
      const ledger = run && run.ledger;
      if (!ledger || !ledger.enabled) {
        resetLedgerStatus("Ledger off.");
        return;
      }
      advisory.ledgerEntry.textContent = String(ledger.entry_id || "?");
      advisory.ledgerSequence.textContent = String(ledger.sequence || "?");
      advisory.ledgerHash.textContent = String(ledger.entry_hash || "?");
      advisory.ledgerReplay.disabled = false;
      setLedgerStatus("Ready to replay verify.", "ok");
    }

    async function replayLedgerEntry() {
      const ledger = latestAdvisoryRun && latestAdvisoryRun.ledger;
      if (!ledger || !ledger.enabled || !ledger.entry_id) {
        resetLedgerStatus("Ledger off.");
        return;
      }
      advisory.ledgerReplay.disabled = true;
      setLedgerStatus("Replaying...", "");
      try {
        const response = await fetch(
          "/advisory/ledger/" + encodeURIComponent(ledger.entry_id) + "/replay",
          { method: "POST" }
        );
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || response.statusText);
        }
        if (payload.verified) {
          setLedgerStatus("Replay verified.", "ok");
        } else {
          const details = Array.isArray(payload.mismatches)
            ? payload.mismatches.join("; ")
            : "unknown mismatch";
          setLedgerStatus("Replay mismatch: " + details, "err");
        }
      } catch (error) {
        setLedgerStatus(
          "Replay failed: " + (error && error.message ? error.message : "unknown error"),
          "err"
        );
      } finally {
        advisory.ledgerReplay.disabled = !(
          latestAdvisoryRun &&
          latestAdvisoryRun.ledger &&
          latestAdvisoryRun.ledger.enabled
        );
      }
    }

    async function runWrapper() {
      advisory.run.disabled = true;
      advisory.load.disabled = true;
      resetLedgerStatus("Waiting for wrapper run.");
      setAdvisoryStatus("running");
      try {
        const count = Number(advisory.count.value || 8);
        const response = await fetch("/advisory/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            seed: advisory.seed.value,
            context: advisory.context.value,
            count: count,
            strictness: advisory.strictness.value,
            source: advisory.source.value
          })
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || response.statusText);
        }
        renderAdvisory(payload);
      } catch (error) {
        latestAdvisoryRun = null;
        advisory.selected.className = "empty";
        advisory.selected.textContent = String(error);
        advisory.inputerSection.hidden = true;
        resetLedgerStatus("Ledger unavailable.");
        setAdvisoryStatus("failed");
      } finally {
        advisory.run.disabled = false;
      }
    }

    function loadSelectedCandidate() {
      if (!latestAdvisoryRun) return;
      const candidate = latestAdvisoryRun.replication_recipe.selected_candidate;
      document.querySelector("#claim").value = candidate.claim;
      document.querySelector("#argument").value = candidate.argument;
      document.querySelector("#context").value = candidate.context;
      document.querySelector("#strictness").value = candidate.strictness;
      setAdvisoryStatus("loaded");
    }

    function setOutputerStatus(message, state) {
      outputer.status.textContent = message;
      outputer.status.className = "outputer-status" + (state ? " " + state : " muted");
    }

    function clearOutputerOutput(emptyMessage) {
      outputer.result.replaceChildren();
      outputer.result.className = "empty";
      outputer.result.textContent = emptyMessage;
    }

    function renderOutputerOutput(payload) {
      // every value rendered via textContent — never innerHTML — because
      // selected_report came from the engine which echoed user text and
      // the LLM also paraphrased user text. Both must stay text-only.
      outputer.result.replaceChildren();
      outputer.result.className = "outputer-output";

      const meta = document.createElement("div");
      meta.className = "outputer-meta";
      const provider = document.createElement("span");
      provider.textContent = "provider: " + (payload.provider || "?");
      const model = document.createElement("span");
      model.textContent = "model: " + (payload.model || "?");
      const cached = document.createElement("span");
      cached.textContent = payload.cached ? "cached" : "fresh";
      const source = document.createElement("span");
      source.textContent = "source: " + (
        payload.validated_output && payload.validated_output.source_report_id
          ? payload.validated_output.source_report_id
          : "?"
      );
      meta.append(provider, model, cached, source);
      outputer.result.appendChild(meta);

      const validated = payload.validated_output || {};
      outputer.result.appendChild(
        outputerSection("Summary", "p", validated.summary || "")
      );
      outputer.result.appendChild(
        outputerSection("Why selected", "p", validated.why_selected || "")
      );
      outputer.result.appendChild(
        outputerListSection("Replication steps", "ol", validated.replication_steps || [])
      );
      outputer.result.appendChild(
        outputerListSection("Caveats", "ul", validated.caveats || [])
      );
    }

    function outputerSection(title, tag, body) {
      const section = document.createElement("div");
      section.className = "outputer-section";
      const h = document.createElement("h4");
      h.textContent = title;
      section.appendChild(h);
      const node = document.createElement(tag);
      node.textContent = body;
      section.appendChild(node);
      return section;
    }

    function outputerListSection(title, tag, items) {
      const section = document.createElement("div");
      section.className = "outputer-section";
      const h = document.createElement("h4");
      h.textContent = title;
      section.appendChild(h);
      const list = document.createElement(tag);
      if (!Array.isArray(items) || items.length === 0) {
        const li = document.createElement("li");
        li.textContent = "(none)";
        list.appendChild(li);
      } else {
        items.forEach(item => {
          const li = document.createElement("li");
          li.textContent = String(item);
          list.appendChild(li);
        });
      }
      section.appendChild(list);
      return section;
    }

    function setOutputerEnabled() {
      outputer.generate.disabled = !latestAdvisoryRun;
      if (latestAdvisoryRun) {
        setOutputerStatus("Ready to generate narration.", "muted");
      }
    }

    async function generateOutputerNarration() {
      if (!latestAdvisoryRun) {
        setOutputerStatus("Run the wrapper first.", "err");
        return;
      }
      outputer.generate.disabled = true;
      setOutputerStatus("Generating...", "muted");
      try {
        const response = await fetch("/advisory/nyahlothep/output", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            selected_report: latestAdvisoryRun.selected_report,
            replication_recipe: latestAdvisoryRun.replication_recipe,
            style: outputer.style.value
          })
        });
        const payload = await response.json();
        if (!response.ok) {
          // Visible error: detail string from FastAPI / outputer validator.
          const message = (payload && payload.detail) ? payload.detail : response.statusText;
          throw new Error(message);
        }
        renderOutputerOutput(payload);
        setOutputerStatus(
          payload.cached ? "Served from cache." : "Generated.",
          payload.cached ? "cached" : "ok"
        );
      } catch (error) {
        clearOutputerOutput("No narration available.");
        setOutputerStatus(
          "Failed: " + (error && error.message ? error.message : "unknown error"),
          "err"
        );
      } finally {
        outputer.generate.disabled = !latestAdvisoryRun;
      }
    }

    function setCopyFeedback(message, state) {
      copyFeedback.textContent = message;
      copyFeedback.className = "copy-feedback" + (state ? " " + state : "");
      if (message) {
        window.setTimeout(() => {
          copyFeedback.textContent = "";
          copyFeedback.className = "copy-feedback";
        }, 2500);
      }
    }

    async function copyJson() {
      const text = fields.json.textContent || "";
      if (!text || text === "{}") {
        setCopyFeedback("Nothing to copy yet — run an evaluation first.", "err");
        return;
      }
      // Clipboard API is gated behind user activation (this click handler).
      // We never copy automatically.
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
          setCopyFeedback("Copied to clipboard.", "ok");
          return;
        }
        throw new Error("Clipboard API unavailable.");
      } catch (error) {
        setCopyFeedback("Copy failed: " + (error && error.message ? error.message : "unknown error"), "err");
      }
    }

    function applyPreset(name) {
      const preset = PRESETS[name];
      if (!preset) return;
      document.querySelector("#claim").value = preset.claim;
      document.querySelector("#argument").value = preset.argument;
      document.querySelector("#context").value = preset.context;
      document.querySelector("#strictness").value = preset.strictness;
    }

    async function evaluate(event) {
      event.preventDefault();
      submit.disabled = true;
      try {
        const body = Object.fromEntries(new FormData(form).entries());
        const response = await fetch("/evaluate_argument", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || response.statusText);
        }
        renderReport(payload);
      } catch (error) {
        fields.json.textContent = String(error);
      } finally {
        submit.disabled = false;
      }
    }

    document.querySelectorAll("button.preset[data-preset]").forEach(btn => {
      btn.addEventListener("click", () => applyPreset(btn.getAttribute("data-preset")));
    });
    copyBtn.addEventListener("click", copyJson);
    advisory.providerFields.check.addEventListener("click", checkProviderStatus);
    advisory.run.addEventListener("click", runWrapper);
    advisory.load.addEventListener("click", loadSelectedCandidate);
    advisory.ledgerReplay.addEventListener("click", replayLedgerEntry);
    outputer.generate.addEventListener("click", generateOutputerNarration);

    form.addEventListener("submit", evaluate);
    fetch("/health")
      .then(r => r.json())
      .then(data => { health.textContent = data.status; })
      .catch(() => { health.textContent = "offline"; });
    checkProviderStatus();
  </script>
</body>
</html>
"""


def render_dashboard_html(nonce: str) -> str:
    return DASHBOARD_HTML.replace("__CSP_NONCE__", nonce)
