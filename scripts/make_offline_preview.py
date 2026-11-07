"""Generate an offline, explicitly synthetic sample using TradingAgents' native report writer.

No market API, LLM, broker or exchange is called. This is a UI rendering
smoke test and never represents an actual model recommendation or backtest.
"""

from pathlib import Path

from tradingagents.reporting import write_report_tree


def main() -> None:
    state = {
        "trade_date": "2026-10-30",
        "market_report": (
            "**SYNTHETIC TEST DATA — NOT MARKET DATA.**\n\n"
            "This preview verifies the report layout only. "
            "No prices, indicators, or real tickers were queried."
        ),
        "sentiment_report": (
            "**Mock sentiment:** Neutral. This is intentionally fabricated text "
            "to exercise the HTML renderer."
        ),
        "news_report": (
            "**Mock news analysis:** No articles fetched; this report is fully offline."
        ),
        "fundamentals_report": (
            "**Mock fundamentals:** No statements or filings fetched."
        ),
        "investment_debate_state": {
            "bull_history": "Synthetic argument for testing only; no bullish recommendation.",
            "bear_history": "Synthetic counterargument for testing only; no bearish recommendation.",
        },
        "investment_plan": (
            "Research manager: this is a layout smoke test, not a strategy."
        ),
        "trader_investment_plan": (
            "Trader: no order is proposed or sent. No broker is connected."
        ),
        "risk_debate_state": {
            "aggressive_history": "Synthetic scenario; capital at risk: zero.",
            "conservative_history": "Synthetic scenario; no market exposure.",
            "neutral_history": "Synthetic scenario; do not infer performance.",
        },
        "final_trade_decision": (
            "**Rating**: Hold\n\n"
            "**OFFLINE MOCK — NOT INVESTMENT ADVICE.** "
            "No LLM, market feed, or broker was used. No trades executed."
        ),
    }
    settings = {
        "llm_provider": "offline-mock",
        "quick_think_llm": "none",
        "deep_think_llm": "none",
        "analysts": ["market", "social", "news", "fundamentals"],
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "version": "0.7.1 (synthetic preview)",
    }
    output = Path("preview/paper-demo")
    report = write_report_tree(
        state, "SYNTHETIC-DEMO", output, settings=settings, html=True
    )
    html = report.with_suffix(".html")
    assert report.is_file() and html.is_file()
    page = html.read_text(encoding="utf-8")
    assert "SYNTHETIC-DEMO" in page
    assert "OFFLINE MOCK" in page
    print(f"Offline preview created: {html}")


if __name__ == "__main__":
    main()
