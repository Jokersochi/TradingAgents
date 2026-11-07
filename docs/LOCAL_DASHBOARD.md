# TradingAgents: локальная панель отчётов (PAPER / READ-ONLY)

Панель показывает уже сохранённые результаты TradingAgents по пяти этапам:
аналитики → исследователи → торговый план → оценка риска → портфельный менеджер.

Она не запускает анализы, не подключается к брокеру, не отправляет ордера,
не выполняет сделки и не требует API-ключей.

## Быстрый запуск на Windows (PowerShell)

Из корня репозитория:

    python --version
    python -m cli.report_dashboard --port 8765

Откройте в браузере: http://127.0.0.1:8765

Панель доступна только на этом компьютере по loopback-адресу.
Если готовых анализов ещё нет, покажет пустое состояние — это ожидаемо.

## Установка и создание первого анализа

Требуется Python 3.11+. В отдельном PowerShell:

    git clone https://github.com/Jokersochi/TradingAgents.git
    cd TradingAgents
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install .

Выберите один из способов доступа к LLM:

1. Укажите ключ одного поддерживаемого провайдера в локальной переменной
   окружения (например, OPENAI_API_KEY). Никогда не коммитьте ключи или .env.
2. Для ChatGPT Plus/Pro можно использовать вход через подписку:
   выполните команду tradingagents login chatgpt и войдите в браузере.
   Запуски расходуют лимиты тарифа.

Далее запустите интерактивно:

    tradingagents

Выберите инструмент, дату, аналитиков, провайдера и сохранение HTML-отчёта.

Для запуска без вопросов необходимо задать провайдера, модели и остальные
параметры TRADINGAGENTS_*, как описано в основном README. Пример CLI
с уже настроенным провайдером:

    tradingagents --ticker AAPL --date 2026-11-06 --analysts market,news --save --no-show

По умолчанию результаты находятся в папке
~/.tradingagents/logs/reports/<ТИКЕР>_<ДАТА>/complete_report.html.
Панель обнаруживает их автоматически (обновление каждые 30 секунд).

Если путь к результатам изменён:

    python -m cli.report_dashboard --results-dir "C:\path\to\logs" --port 8765

Аргумент --results-dir указывает на родительскую папку reports,
а не на саму папку reports.

## Docker

Сохраните .env только локально. Для доступа к отчётам с хоста используйте
TRADINGAGENTS_DATA_DIR=./data с docker-compose. Запуск:

    docker compose run --rm tradingagents

Файлы будут в ./data/logs/reports; панель на хосте:

    python -m cli.report_dashboard --results-dir "./data/logs"

## Проверки

    python -m pip install -e ".[dev]"
    pytest -q tests/test_cli_report_dashboard.py
    ruff check cli/report_dashboard.py tests/test_cli_report_dashboard.py

CI выполняет существующий набор тестов и линтер всего репозитория.
HTTP-панель разрешает только GET / и GET /report/<имя>; POST запрещён.
Папки-симлинки и выход за каталог результатов не допускаются.
Ответы снабжены CSP, метаданные экранируются для HTML.

Важно: визуальные статусы обозначают наличие файлов с отчётами, а не качество
прогноза, текущую работу агентов, исполнение торговой заявки или доходность.
