"""Smoke and security checks for the local, read-only report dashboard."""

from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cli.report_dashboard import discover_runs, make_handler, render_index


def _report(results, name="AAPL_20261108", ticker="AAPL", rating="Hold"):
    folder = results / "reports" / name
    folder.mkdir(parents=True)
    (folder / "complete_report.html").write_text("<!doctype html><title>Report</title>", encoding="utf-8")
    (folder / "complete_report.md").write_text(
        f"# Trading Analysis Report: {ticker}\n\n"
        "- Analysis date: 2026-11-07\n"
        f"- Rating: {rating}\n"
        "- Generated: 2026-11-08 01:00\n\n"
        "## I. Analyst Team Reports\n",
        encoding="utf-8",
    )
    return folder


@pytest.mark.unit
def test_empty_dashboard_has_no_fabricated_trades(tmp_path):
    assert discover_runs(tmp_path) == []
    page = render_index([])
    assert "Готовых HTML-отчётов пока нет" in page
    assert "READ-ONLY" in page
    assert "Аналитики" in page and "Решение" in page


@pytest.mark.unit
def test_report_metadata_and_stage_detection(tmp_path):
    folder = _report(tmp_path)
    stage = folder / "1_analysts"
    stage.mkdir()
    (stage / "market.md").write_text("Observed market", encoding="utf-8")

    runs = discover_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0]["ticker"] == "AAPL"
    assert runs[0]["rating"] == "Hold"
    assert runs[0]["date"] == "2026-11-07"
    assert runs[0]["generated"] == "2026-11-08 01:00"
    assert runs[0]["stages"] == [True, False, False, False, False]
    assert 'href="/report/AAPL_20261108"' in render_index(runs)


@pytest.mark.unit
def test_report_headers_are_html_escaped(tmp_path):
    _report(tmp_path, ticker="<script>alert(1)</script>", rating='Buy"><img src=x>')
    page = render_index(discover_runs(tmp_path))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<img src=x>" not in page
    assert "&lt;img src=x&gt;" in page


@pytest.mark.unit
def test_symlinked_reports_cannot_escape_results_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "complete_report.html").write_text("outside", encoding="utf-8")
    root = tmp_path / "results"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "outside").symlink_to(outside, target_is_directory=True)
    assert discover_runs(root) == []


@pytest.mark.unit
def test_http_viewer_serves_only_safe_reports_and_rejects_post(tmp_path):
    _report(tmp_path)
    handler = make_handler(tmp_path)
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/", timeout=3) as response:
                assert response.status == 200
                assert "AAPL" in response.read().decode()
                assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
            with urlopen(base + "/report/AAPL_20261108", timeout=3) as response:
                assert response.status == 200
                assert b"<title>Report</title>" in response.read()
            for path in ("/report/%2e%2e", "/report/..%2foutside", "/missing"):
                with pytest.raises(HTTPError) as error:
                    urlopen(base + path, timeout=3)
                assert error.value.code == 404
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + "/", method="POST"), timeout=3)
            assert error.value.code == 405
        finally:
            server.shutdown()
            worker.join(timeout=3)
