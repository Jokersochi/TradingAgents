"""Checks for conservative saved-report screening, without live market access."""

import os
from datetime import datetime, timedelta

import pytest

from cli.report_dashboard import discover_runs, render_index
from cli.report_quality import assess_saved_run


def _saved_run(root, market):
    folder = root / "reports" / "AAPL_20261116_test"
    section = folder / "1_analysts"
    section.mkdir(parents=True)
    (section / "market.md").write_text(market, encoding="utf-8")
    (folder / "complete_report.html").write_text("<html>sample</html>", encoding="utf-8")
    (folder / "complete_report.md").write_text(
        "# Trading Analysis Report: AAPL\n\n"
        "- Analysis date: 2026-11-13\n"
        "- Rating: Hold\n"
        "- Generated: 2026-11-16 03:00\n",
        encoding="utf-8",
    )
    return folder


def _log(root):
    folder = root / "AAPL" / "2026-11-13"
    folder.mkdir(parents=True)
    path = folder / "message_tool.log"
    path.write_text(
        "02:55 [Tool Call] get_stock_data(start_date=2026-11-06, end_date=2026-11-13)\n"
        "02:55 [Tool Call] get_verified_market_snapshot(curr_date=2026-11-13)\n"
        "02:55 [Data] ## atr values from 2026-10-14 to 2026-11-13: 2026-11-13: 8.21\n"
        "02:55 [Data] ## close_200_sma values from 2026-10-14 to 2026-11-13: "
        "2026-11-13: 300.77\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.unit
def test_trace_only_report_is_flagged_in_dashboard(tmp_path):
    _saved_run(tmp_path, '[Called get_indicators({"indicator": "macd"})]')
    result = assess_saved_run(
        tmp_path / "reports" / "AAPL_20261116_test",
        tmp_path, "AAPL", "2026-11-13",
    )
    assert result.status == "issues"
    assert any("короткий" in issue for issue in result.issues)
    assert any("след вызова" in issue for issue in result.issues)
    page = render_index(discover_runs(tmp_path))
    assert "Автопроверка: есть замечания" in page
    assert "Вместо выводов" in page


@pytest.mark.unit
def test_indicator_contradictions_are_flagged_with_compatible_log(tmp_path):
    market = (
        "# Анализ AAPL за 2026-11-13\n"
        + ("RSI 60.90, MACD 4.21, цена выше SMA. " * 25)
        + "\n| Индикатор | Значение | Вывод |\n"
        + "|---|---|---|\n"
        + "| ATR (Волатильность) | ❌ Не получен | Нет данных |\n"
        + "| Close 200 SMA | ❌ Не получен | Нет данных |\n"
    )
    folder = _saved_run(tmp_path, market)
    log = _log(tmp_path)
    page = folder / "complete_report.html"
    now = datetime.now().timestamp()
    os.utime(log, (now - 60, now - 60))
    os.utime(page, (now, now))
    result = assess_saved_run(folder, tmp_path, "AAPL", "2026-11-13")
    assert result.status == "issues"
    assert any("ATR:" in issue for issue in result.issues)
    assert any("200 SMA:" in issue for issue in result.issues)


@pytest.mark.unit
def test_newer_log_does_not_verify_an_older_report(tmp_path):
    folder = _saved_run(tmp_path, "2026-11-13 RSI 60.90, MACD 4.21. " * 30)
    log = _log(tmp_path)
    page = folder / "complete_report.html"
    now = datetime.now().timestamp()
    os.utime(page, (now, now))
    newer = now + timedelta(hours=1).total_seconds()
    os.utime(log, (newer, newer))
    result = assess_saved_run(folder, tmp_path, "AAPL", "2026-11-13")
    assert result.status == "unknown"
    assert not result.issues


@pytest.mark.unit
def test_compatible_log_without_heuristic_issues_is_screened_not_certified(tmp_path):
    folder = _saved_run(tmp_path, "2026-11-13 RSI 60.90, MACD 4.21. " * 30)
    log = _log(tmp_path)
    now = datetime.now().timestamp()
    os.utime(log, (now - 30, now - 30))
    os.utime(folder / "complete_report.html", (now, now))
    result = assess_saved_run(folder, tmp_path, "AAPL", "2026-11-13")
    assert result.status == "screened"
    assert result.issues == ()
    html = render_index(discover_runs(tmp_path))
    assert "явных несоответствий не найдено" in html
    assert "не подтверждает достоверность прогноза" in html


@pytest.mark.unit
def test_symlinked_market_report_is_not_followed(tmp_path):
    folder = _saved_run(tmp_path, "2026-11-13 RSI 60.90 " * 50)
    outside = tmp_path / "outside.md"
    outside.write_text("SECRET_NEVER_RENDER", encoding="utf-8")
    market = folder / "1_analysts" / "market.md"
    market.unlink()
    market.symlink_to(outside)
    result = assess_saved_run(folder, tmp_path, "AAPL", "2026-11-13")
    assert result.status == "unknown"
    assert "SECRET_NEVER_RENDER" not in render_index(discover_runs(tmp_path))
