"""Local blotter. It only replays the paper cycle."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from desk.session import halt, load_report, resume, run_paper, state_dir


def serve(port: int) -> None:
    server = make_server(port)
    print(f"Dashboard paper: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")
    finally:
        server.server_close()


def make_server(port: int) -> ThreadingHTTPServer:
    directory = state_dir("web")
    handler = _handler(directory)
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def _handler(directory):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/report":
                self._send(200, "application/json", json.dumps(load_report(directory) or {}).encode())
                return
            if path in ("/", "/index.html"):
                report = load_report(directory)
                self._send(200, "text/html; charset=utf-8", render_page(report).encode())
                return
            self._send(404, "text/plain", b"not found")

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/cycle":
                report = run_paper(directory, reset=True)
                self._send(200, "application/json", json.dumps(report).encode())
                return
            if path == "/api/halt":
                halt(directory, "dihentikan dari dashboard")
                self._send(200, "application/json", b'{"ok":true}')
                return
            if path == "/api/resume":
                resume(directory)
                self._send(200, "application/json", b'{"ok":true}')
                return
            self._send(404, "text/plain", b"not found")

        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def render_page(report: dict | None) -> str:
    equity = "Belum dijalankan"
    body = "<p class='muted'>Belum ada siklus. Tombol di bawah memutar ulang data fixture.</p>"
    if report:
        equity = f"{report['equity_usd']:,.2f} USD"
        body = _report_html(report)
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paired desk</title>
<style>
  :root {{ color-scheme: dark; --bg: #16130f; --panel: #221c16; --line: #3a3126; --ink: #f3eadb; --muted: #b3a48f; --amber: #e6a15c; --good: #8fbf8a; --bad: #d47a6a; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 15px/1.5 "Iowan Old Style", Palatino, Georgia, serif; background: var(--bg); color: var(--ink); }}
  main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-weight: 500; letter-spacing: -0.03em; margin: 0 0 4px; }}
  .muted {{ color: var(--muted); }}
  .row {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin: 20px 0; }}
  button {{ font: inherit; background: var(--amber); color: #23180e; border: 0; border-radius: 999px; padding: 8px 16px; cursor: pointer; }}
  button.ghost {{ background: transparent; color: var(--ink); border: 1px solid var(--line); }}
  .equity {{ font-variant-numeric: tabular-nums; font-size: 42px; letter-spacing: -0.04em; margin: 8px 0 0; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 18px 0; }}
  .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; }}
  .card b {{ display: block; font-weight: 500; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 22px; }}
  th, td {{ text-align: left; padding: 7px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 500; font-size: 13px; }}
  svg {{ width: 100%; height: 160px; background: #1b1713; border-radius: 12px; }}
  polyline {{ fill: none; stroke: var(--amber); stroke-width: 2; }}
  .good {{ color: var(--good); }}
  .bad {{ color: var(--bad); }}
</style>
</head>
<body>
<main>
  <p class="muted">Paper saja. Lima repositori tetap pada perannya.</p>
  <h1>Paired desk</h1>
  <p class="equity" id="equity">{equity}</p>
  <div class="grid">
    <div class="card"><b>Vibe-Trading</b><span class="muted">Gerbang backtest sebelum ada order.</span></div>
    <div class="card"><b>AI Hedge Fund</b><span class="muted">Suara komite untuk ekuitas. Buku paper.</span></div>
    <div class="card"><b>Hummingbot</b><span class="muted">Eksekusi BTC-USDT. Paper trade bawaan.</span></div>
    <div class="card"><b>pump.fun / bonk.fun</b><span class="muted">Jalur launch, hanya bila kripto risk-on.</span></div>
    <div class="card"><b>Grok Build</b><span class="muted">Operator. Tidak memegang kunci dompet.</span></div>
  </div>
  <div class="row">
    <button type="button" id="cycle">Jalankan siklus paper</button>
    <button type="button" class="ghost" id="halt">Hentikan</button>
    <button type="button" class="ghost" id="resume">Lanjutkan</button>
  </div>
  <div id="body">{body}</div>
</main>
<script>
async function post(url) {{
  const response = await fetch(url, {{method: "POST"}});
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}}
document.getElementById("cycle").onclick = async () => {{
  await post("/api/cycle");
  location.reload();
}};
document.getElementById("halt").onclick = async () => {{
  await post("/api/halt");
  await post("/api/cycle");
  location.reload();
}};
document.getElementById("resume").onclick = async () => {{
  await post("/api/resume");
  await post("/api/cycle");
  location.reload();
}};
</script>
</body>
</html>
"""


def _report_html(report: dict) -> str:
    rows = []
    for card in report.get("research", {}).values():
        klass = "good" if card["passed"] else "bad"
        rows.append(
            "<tr>"
            f"<td>{_esc(card['symbol'])}</td>"
            f"<td class='{klass}'>{_esc(card['reason'])}</td>"
            f"<td>{card['total_return']:.2%}</td>"
            f"<td>{card['max_drawdown']:.2%}</td>"
            "</tr>"
        )
    decisions = []
    for decision in report.get("decisions", {}).values():
        decisions.append(
            "<tr>"
            f"<td>{_esc(decision['symbol'])}</td>"
            f"<td>{_esc(decision['action'])}</td>"
            f"<td>{decision['score']:+.2f}</td>"
            f"<td>{_esc(decision['venue'])}</td>"
            "</tr>"
        )
    launches = []
    for launch in report.get("launches", []):
        launches.append(
            "<tr>"
            f"<td>{_esc(launch['symbol'])}</td>"
            f"<td>{_esc(launch['platform'])}</td>"
            f"<td>{_esc(launch['status'])}</td>"
            f"<td>{_esc(launch['reason'])}</td>"
            f"<td>{launch.get('pnl_sol', 0):+.6f}</td>"
            "</tr>"
        )
    killed = ""
    if report.get("killed"):
        killed = f"<p class='bad'>Kill switch: {_esc(str(report['killed']))}</p>"
    return f"""
{killed}
{_svg(report.get("curve") or [])}
<h2>Riset</h2>
<table><tr><th>Nama</th><th>Gerbang</th><th>Imbal</th><th>Drawdown</th></tr>{''.join(rows)}</table>
<h2>Komite</h2>
<table><tr><th>Nama</th><th>Aksi</th><th>Skor</th><th>Venue</th></tr>{''.join(decisions) or '<tr><td colspan="4">Tidak ada</td></tr>'}</table>
<h2>Launchpad</h2>
<table><tr><th>Nama</th><th>Platform</th><th>Status</th><th>Alasan</th><th>PnL SOL</th></tr>{''.join(launches)}</table>
<p class="muted">Kas USD {report['cash_usd']:.2f} · kas SOL {report['cash_sol']:.6f} · {len(report.get('fills', []))} fill</p>
"""


def _svg(curve: list[dict]) -> str:
    if len(curve) < 2:
        return ""
    values = [float(point["equity"]) for point in curve]
    low, high = min(values), max(values)
    span = high - low or 1.0
    width, height = 640, 160
    points = []
    for index, value in enumerate(values):
        x = index / (len(values) - 1) * width
        y = height - ((value - low) / span) * (height - 16) - 8
        points.append(f"{x:.1f},{y:.1f}")
    return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Kurva ekuitas"><polyline points="{" ".join(points)}" /></svg>'


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
