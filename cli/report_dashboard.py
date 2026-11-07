"""Local read-only dashboard for saved TradingAgents reports.

This server never invokes the trading graph, connects to a broker, or changes files.
It binds to the loopback interface, not to a publicly accessible address.
"""

import argparse
import os
from contextlib import suppress
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

STAGES = (
    ("Аналитики", "1_analysts"),
    ("Исследование", "2_research"),
    ("Торговый план", "3_trading"),
    ("Оценка риска", "4_risk"),
    ("Решение", "5_portfolio"),
)
MAX_REPORTS = 100

STYLE = """
:root { color-scheme: dark; --bg:#0b1020; --panel:#151c2f; --line:#2a344b;
  --ink:#edf1fb; --muted:#9faec9; --accent:#7bd9bd; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1200px; margin:0 auto; padding:40px 24px 80px; }
a { color:inherit; text-decoration:none; }
a:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
header { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }
.eyebrow { color:var(--accent); text-transform:uppercase; font-size:12px; font-weight:700; letter-spacing:.13em; }
h1 { font-size:clamp(30px,4vw,52px); line-height:1.14; margin:12px 0; letter-spacing:-.04em; }
h2 { font-size:20px; margin:32px 0 16px; }
p { margin:8px 0; color:var(--muted); }
.pill { color:var(--accent); border:1px solid #356c66; border-radius:999px; padding:9px 15px; white-space:nowrap; }
.hero { padding:35px; margin-top:28px; background:linear-gradient(120deg,#1d3547,#141b31 70%);
  border:1px solid var(--line); border-radius:22px; }
.hero strong { color:var(--ink); }
.stats { display:flex; flex-wrap:wrap; gap:24px; margin-top:24px; }
.metric { min-width:130px; }
.metric b { display:block; font-size:28px; font-variant-numeric:tabular-nums; }
.metric span { color:var(--muted); font-size:13px; }
.flow { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:9px; }
.step { position:relative; padding:18px 13px; background:var(--panel); border:1px solid var(--line);
  border-radius:14px; min-height:116px; }
.step .number { color:var(--accent); font-size:12px; }
.step b { display:block; margin-top:10px; font-size:14px; }
.step small { color:var(--muted); }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(275px,1fr)); gap:14px; }
.card { border:1px solid var(--line); border-radius:16px; background:var(--panel); padding:22px;
  transition:border-color .15s,transform .15s; }
.card:hover { border-color:var(--accent); transform:translateY(-2px); }
.card .head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.ticker { font-size:23px; font-weight:750; letter-spacing:-.03em; overflow-wrap:anywhere; }
.rating { display:inline-block; padding:4px 9px; border:1px solid #47516b; border-radius:7px;
  color:var(--accent); font-size:12px; font-weight:700; white-space:nowrap; }
.meta { margin-top:18px; color:var(--muted); font-size:13px; overflow-wrap:anywhere; }
.stages { display:flex; gap:5px; margin-top:16px; }
.dot { display:block; flex:1; height:5px; background:#38425b; border-radius:5px; }
.dot.done { background:var(--accent); }
.open { color:var(--accent); font-weight:600; margin-top:18px; }
.empty { border:1px dashed var(--line); padding:30px; border-radius:16px; }
footer { color:var(--muted); margin-top:40px; font-size:12px; }
@media(max-width:750px) { main{padding:22px 15px 55px;} header{display:block;}
  .pill{display:inline-block;margin-top:12px;} .hero{padding:24px;} .flow{grid-template-columns:1fr 1fr;}
}
@media(prefers-reduced-motion:reduce){.card{transition:none;}.card:hover{transform:none;}}
"""


def default_results_dir() -> Path:
    override = os.environ.get("TRADINGAGENTS_RESULTS_DIR")
    return Path(override).expanduser() if override else Path.home() / ".tradingagents" / "logs"


def _header_fields(report: Path) -> dict[str, str]:
    """Read only the report header, never expose its body in the index."""
    fields = {}
    if not report.is_file() or report.is_symlink():
        return fields
    with report.open("r", encoding="utf-8", errors="replace") as source:
        header = source.read(8192).split("\n## ", 1)[0]
    for line in header.splitlines():
        if line.startswith("# Trading Analysis Report: "):
            fields["ticker"] = line.removeprefix("# Trading Analysis Report: ").strip()
        elif line.startswith("- "):
            key, separator, value = line[2:].partition(": ")
            if separator and key in {"Rating", "Analysis date", "Generated"}:
                fields[key] = value.strip()
    return fields


def discover_runs(results_dir: Path) -> list[dict]:
    root = (results_dir / "reports").resolve()
    if not root.is_dir():
        return []
    runs = []
    for folder in root.iterdir():
        if not folder.is_dir() or folder.is_symlink():
            continue
        page = folder / "complete_report.html"
        if not page.is_file() or page.is_symlink() or not page.resolve().is_relative_to(root):
            continue
        markdown = folder / "complete_report.md"
        fields = _header_fields(markdown) if markdown.resolve().is_relative_to(root) else {}
        mtime = page.stat().st_mtime
        runs.append({
            "slug": folder.name,
            "ticker": fields.get("ticker") or folder.name,
            "rating": fields.get("Rating", "Нет оценки"),
            "date": fields.get("Analysis date", "Дата не указана"),
            "generated": fields.get("Generated", datetime.fromtimestamp(mtime).astimezone().strftime("%Y-%m-%d %H:%M")),
            "modified": mtime,
            "stages": [bool((folder / name).is_dir() and any((folder / name).glob("*.md"))) for _, name in STAGES],
            "page": page,
        })
    runs.sort(key=lambda run: run["modified"], reverse=True)
    return runs[:MAX_REPORTS]


def render_index(runs: list[dict]) -> str:
    cards = []
    for run in runs:
        dots = "".join(
            f'<span class="dot{" done" if done else ""}" title="{escape(name, quote=True)}: {"готов" if done else "нет отчёта"}"></span>'
            for (name, _), done in zip(STAGES, run["stages"], strict=True)
        )
        cards.append(
            '<a class="card" href="/report/' + quote(run["slug"], safe="") + '">'
            '<div class="head"><span class="ticker">' + escape(run["ticker"]) + '</span>'
            '<span class="rating">' + escape(run["rating"]) + '</span></div>'
            '<div class="meta">Дата анализа: ' + escape(run["date"]) + '<br>'
            'Сформировано: ' + escape(run["generated"]) + '</div>'
            '<div class="stages" aria-label="Наличие отчётов по пяти этапам">' + dots + '</div>'
            '<div class="open">Открыть отчёт →</div></a>'
        )
    if not cards:
        cards.append(
            '<div class="empty"><strong>Готовых HTML-отчётов пока нет.</strong>'
            '<p>Запустите анализ через TradingAgents CLI с сохранением отчёта. '
            'Панель автоматически обнаружит результаты.</p></div>'
        )
    flow = "".join(
        f'<div class="step"><span class="number">0{index}</span><b>{escape(name)}</b>'
        f'<small>{escape(folder)}</small></div>'
        for index, (name, folder) in enumerate(STAGES, start=1)
    )
    latest = escape(runs[0]["ticker"]) if runs else "—"
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30"><title>TradingAgents — локальный монитор</title>
<style>{STYLE}</style></head>
<body><main><header><div><div class="eyebrow">TradingAgents / наблюдение</div>
<h1>Обзор работы агентов</h1>
<p>Локальный просмотр результатов без торговых операций и доступа к API.</p></div>
<span class="pill">READ-ONLY · PAPER</span></header>
<section class="hero"><strong>Статус отчётов</strong>
<p>Каждая карточка отражает сохранённый анализ, а не активную биржевую позицию.</p>
<div class="stats"><div class="metric"><b>{len(runs)}</b><span>последних анализов</span></div>
<div class="metric"><b>{latest}</b><span>последний инструмент</span></div>
<div class="metric"><b>30 с</b><span>обновление страницы</span></div></div></section>
<h2>Как принимается решение</h2><section class="flow" aria-label="Пять этапов анализа">{flow}</section>
<h2>Сохранённые анализы</h2><section class="grid">{"".join(cards)}</section>
<footer>Только чтение · источник: локальные complete_report.html · без ордеров и брокерских подключений</footer>
</main></body></html>"""


def make_handler(results_dir: Path):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _reply(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            runs = discover_runs(results_dir)
            if path == "/":
                body = render_index(runs).encode("utf-8")
                self._reply(200, body, "text/html; charset=utf-8")
                return
            if path.startswith("/report/"):
                slug = unquote(path.removeprefix("/report/"))
                if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
                    self.send_error(404)
                    return
                match = next((run for run in runs if run["slug"] == slug), None)
                if match is not None:
                    self._reply(200, match["page"].read_bytes(), "text/html; charset=utf-8")
                    return
            self.send_error(404)

        def do_POST(self) -> None:
            self.send_error(405)

    return DashboardHandler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local, read-only TradingAgents run viewer")
    parser.add_argument("--results-dir", type=Path, default=default_results_dir())
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    # No --host option: a dashboard containing financial reports must stay local.
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.results_dir)) as server:
        print(f"TradingAgents report monitor: http://127.0.0.1:{server.server_port}")
        print(f"Read-only results directory: {args.results_dir / 'reports'}")
        with suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
