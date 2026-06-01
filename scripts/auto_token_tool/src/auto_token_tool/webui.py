from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .sdk import AutoTokenTool


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auto Token Tool</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, Segoe UI, Arial, sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #1d2430; }
    header { padding: 18px 24px; border-bottom: 1px solid #d7dce2; background: #ffffff; }
    h1 { margin: 0; font-size: 20px; font-weight: 650; }
    main { max-width: 1120px; margin: 0 auto; padding: 24px; }
    .toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; }
    button { border: 1px solid #b9c2ce; background: #fff; color: #1d2430; border-radius: 6px; padding: 8px 12px; cursor: pointer; }
    button:hover { background: #eef2f6; }
    table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d7dce2; }
    th, td { padding: 10px 12px; border-bottom: 1px solid #e5e8ed; text-align: left; font-size: 14px; }
    th { background: #f0f3f7; font-weight: 650; }
    .status { font-size: 13px; color: #5c6675; }
    .pill { display: inline-block; border-radius: 999px; padding: 2px 8px; border: 1px solid #c8d0da; font-size: 12px; }
    .plus { background: #e9f7ef; border-color: #9bd7b3; color: #166534; }
    .free { background: #fff7df; border-color: #e8c766; color: #7c5b00; }
    @media (prefers-color-scheme: dark) {
      body { background: #101318; color: #e7ebf0; }
      header, table, button { background: #171b22; color: #e7ebf0; border-color: #303743; }
      th { background: #202631; }
      th, td { border-bottom-color: #2b323d; }
      button:hover { background: #222936; }
      .status { color: #aeb7c4; }
    }
  </style>
</head>
<body>
  <header><h1>Auto Token Tool</h1></header>
  <main>
    <div class="toolbar">
      <button id="reload">Refresh View</button>
      <button id="refreshApi">Refresh From API</button>
      <span class="status" id="status"></span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Email</th><th>Level</th><th>Credits</th><th>Share Code</th><th>Token</th><th>Updated</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </main>
  <script>
    const rows = document.getElementById("rows");
    const statusEl = document.getElementById("status");
    function pill(level) {
      const cls = String(level || "").toLowerCase() === "plus" ? "plus" : "free";
      return `<span class="pill ${cls}">${escapeHtml(level || "unknown")}</span>`;
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }
    async function load(refresh=false) {
      statusEl.textContent = refresh ? "Refreshing account status..." : "Loading...";
      const res = await fetch(`/api/accounts${refresh ? "?refresh=1" : ""}`);
      const data = await res.json();
      rows.innerHTML = data.accounts.map(acc => `<tr>
        <td>${escapeHtml(acc.email || acc.nickname || acc.user_id)}</td>
        <td>${pill(acc.package_level)}</td>
        <td>${escapeHtml(acc.total_credit ?? "")}</td>
        <td>${escapeHtml(acc.share_code || "")}</td>
        <td>${escapeHtml(acc.token_masked || "")}</td>
        <td>${escapeHtml(acc.updated_at || "")}</td>
      </tr>`).join("");
      statusEl.textContent = `${data.accounts.length} account(s), updated ${new Date().toLocaleTimeString()}`;
    }
    document.getElementById("reload").addEventListener("click", () => load(false));
    document.getElementById("refreshApi").addEventListener("click", () => load(true));
    load(false);
  </script>
</body>
</html>"""


def serve(tool: AutoTokenTool, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(HTML)
                return
            if parsed.path == "/api/accounts":
                query = parse_qs(parsed.query)
                accounts = (
                    tool.refresh_accounts()
                    if query.get("refresh", ["0"])[0] == "1"
                    else tool.list_accounts()
                )
                payload = {
                    "accounts": [
                        account.to_dict(include_token=False, include_raw=False)
                        for account in accounts
                    ]
                }
                self._send_json(payload)
                return
            self.send_error(404)

        def log_message(self, fmt: str, *args) -> None:
            return

        def _send_html(self, text: str) -> None:
            raw = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _send_json(self, data: dict) -> None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"WebUI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWebUI stopped.")
    finally:
        server.server_close()
