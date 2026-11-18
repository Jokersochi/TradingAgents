"""Read-only, heuristic screening of saved reports (never certifies trade quality).

This checks basic completeness and a few verifiable contradictions. It never
calls an LLM, fetches market data, places orders, or modifies local files.
"""

import re
from dataclasses import dataclass
from pathlib import Path

MAX_MARKET_CHARS = 150_000
MAX_LOG_CHARS = 750_000
LOG_MATCH_WINDOW_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class QualityCheck:
    status: str  # "issues", "screened", or "unknown"
    issues: tuple[str, ...] = ()


def _read_file(path: Path, limit: int) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as file:
        return file.read(limit + 1)


def _compatible_log(log: Path, page: Path) -> bool:
    """Reject logs that clearly come from a later run or an unrelated period."""
    return (
        not log.is_symlink()
        and log.is_file()
        and page.stat().st_mtime - LOG_MATCH_WINDOW_SECONDS <= log.stat().st_mtime
        <= page.stat().st_mtime + 1
    )


def assess_saved_run(folder: Path, logs_root: Path, ticker: str, date: str) -> QualityCheck:
    """Screen a specific saved report, with no claim of financial correctness."""
    market = folder / "1_analysts" / "market.md"
    try:
        body = _read_file(market, MAX_MARKET_CHARS)
        if body is None:
            return QualityCheck("unknown")
        issues: list[str] = []
        if len(body) > MAX_MARKET_CHARS:
            issues.append("Рыночный раздел превышает лимит автоматической проверки")
        if len(body.strip()) < 600:
            issues.append("Рыночный раздел слишком короткий")
        if body.lstrip().startswith("[Called ") or body.count("[Called ") > 1:
            issues.append("Вместо выводов присутствует след вызова инструмента")
        if not re.search(r"\b\d+(?:[.,]\d+)?\b", body):
            issues.append("Нет числовых наблюдений в рыночном разделе")

        # The mutable per-ticker log can belong to another run. Only use it
        # when its timestamps are compatible with this immutable HTML report.
        matched_log = False
        if re.fullmatch(r"[A-Za-z0-9.^_-]{1,20}", ticker) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", date
        ):
            log = logs_root / ticker / date / "message_tool.log"
            page = folder / "complete_report.html"
            if page.is_file() and not page.is_symlink() and _compatible_log(log, page):
                source = _read_file(log, MAX_LOG_CHARS)
                if source is not None and len(source) <= MAX_LOG_CHARS:
                    matched_log = True
                    for indicator, label in (("atr", "ATR"), ("close_200_sma", "200 SMA")):
                        data = re.search(
                            rf"## {re.escape(indicator)} values from [^\n]*{re.escape(date)}:",
                            source,
                        )
                        denial = re.search(
                            rf"(?im)^\|[^\n]*{re.escape(label)}[^\n]*\|[^\n]*"
                            r"(?:не получен|нет данных|отсутствует)",
                            body,
                        )
                        if data and denial:
                            issues.append(f"{label}: данные получены, но отчёт утверждает обратное")
        if issues:
            return QualityCheck("issues", tuple(issues))
        return QualityCheck("screened" if matched_log else "unknown")
    except OSError:
        return QualityCheck("unknown")
