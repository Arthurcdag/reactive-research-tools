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

    button:disabled {
      cursor: wait;
      opacity: 0.65;
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
          <button class="secondary" type="button" id="load-clean">Clean case</button>
        </div>
      </form>
    </section>

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
    const fields = {
      polarity: document.querySelector("#polarity"),
      recommendation: document.querySelector("#recommendation"),
      effectiveness: document.querySelector("#effectiveness"),
      bogusness: document.querySelector("#bogusness"),
      issues: document.querySelector("#issues"),
      trace: document.querySelector("#trace"),
      probes: document.querySelector("#probes"),
      json: document.querySelector("#json")
    };

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

    function renderReport(report) {
      fields.polarity.textContent = report.effective_polarity;
      fields.recommendation.textContent = report.recommendation;
      fields.effectiveness.textContent = Number(report.effectiveness_score).toFixed(3);
      fields.bogusness.textContent = Number(report.bogusness_score).toFixed(3);
      fields.json.textContent = JSON.stringify(report, null, 2);

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

    document.querySelector("#load-clean").addEventListener("click", () => {
      document.querySelector("#claim").value = "P";
      document.querySelector("#argument").value = "It is not the case that not P. Therefore P.";
      document.querySelector("#context").value = "logic";
    });

    form.addEventListener("submit", evaluate);
    fetch("/health")
      .then(r => r.json())
      .then(data => { health.textContent = data.status; })
      .catch(() => { health.textContent = "offline"; });
  </script>
</body>
</html>
"""


def render_dashboard_html(nonce: str) -> str:
    return DASHBOARD_HTML.replace("__CSP_NONCE__", nonce)
