# Reward Hacking in LLM Agents — Baseline v1.0

Наблюдательный baseline для независимых coding-эпизодов через Groq
`openai/gpt-oss-20b`. Агент может редактировать публичные тесты в своей
Docker-среде; внешний контроллер сохраняет траекторию и независимо проверяет
зафиксированное решение. Штрафов, XP, обучения, обратной связи аудита и памяти
между эпизодами нет.

Научные источники изучены по пяти локальным PDF. Методологические заимствования:
[обзор литературы](docs/literature_review.md). Расхождения с ТЗ:
[methodological_differences.md](docs/methodological_differences.md).
Точный протокол: [experimental_protocol.md](docs/experimental_protocol.md).
Фактический checkpoint: [baseline_results.md](docs/baseline_results.md).
Полный список файлов: [implementation_inventory.md](docs/implementation_inventory.md).

## Установка

Нужны Python 3.11+ и Docker с Linux-контейнерами. Команды PowerShell выполняются
из корня репозитория:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker build --tag safety-games-sandbox:local sandbox
```

В существующем локальном `.env` или окружении контроллера задайте
`GROQ_API_KEY`; шаблон — `.env.example`. Ключ не передаётся в контейнер,
промпты или журналы. Runtime-зависимость одна: `python-dotenv`. HTTP-клиент,
конфигурация TOML и тесты используют стандартную библиотеку.
Для графиков отдельно доступен optional extra `.[analysis]`; для повторного
извлечения PDF — `.[research]`. Эти пакеты не нужны для самого агента.

## Проверки перед запуском

```powershell
.\.venv\Scripts\python.exe -m safety_games check-config --config configs/baseline_v1.toml
.\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v
$env:SAFETY_GAMES_DOCKER_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.test_sandbox_integration tests.test_episode_integration -v
Remove-Item Env:SAFETY_GAMES_DOCKER_TESTS
.\.venv\Scripts\python.exe -m safety_games validate-tasks
.\.venv\Scripts\python.exe -m safety_games api-check
```

Unit-тесты работают без API-ключа и Docker; 12 настоящих контейнерных проверок
включаются переменной окружения. При явном включении недоступный Docker означает
ошибку. Проверка эталонов запускает все 15 решений с подготовленными тестами в
Docker и сохраняет `results/reference_validation.json`; это проверка
инфраструктуры, не результаты поведения LLM. `api-check` проверяет список моделей
без генерации.

## Реальные эпизоды и возобновление

```powershell
.\.venv\Scripts\python.exe -m safety_games run --config configs/baseline_v1.toml --experiment-id baseline-v1-r2 --stage smoke
.\.venv\Scripts\python.exe -m safety_games run --config configs/baseline_v1.toml --experiment-id baseline-v1-r2 --stage pilot --resume
```

Smoke заранее выбирает `lc217`, `lc4`, `abc389_e`: по одной задаче каждого уровня.
Pilot продолжает тот же запуск на остальных задачах, не повторяя завершённые.
Для нового независимого запуска выберите новый experiment ID.

Каждый эпизод имеет новый контекст и отдельный контейнер. Доступны только
`list_files`, `read_file`, `write_file`, `run_command`, `finish_task`.
Встроенные инструменты и интернет-поиск провайдера не включаются.
CLI разрешает только согласованный endpoint/model; смена провайдера требует
отдельного протокола. Обработка особенностей Groq описана в
[technical_changes.md](docs/technical_changes.md).

Контроллер сохраняет состояние после эпизодов и отдельных независимых тестов.
После обычного прерывания используйте ту же команду с `--resume`.
Незавершённый агентный этап начинает новую попытку с чистым контекстом, сохраняя
прежнюю траекторию; завершённое решение на стадии оценивания повторно к LLM
не отправляется. Изменение кода, конфигурации, образа, промпта или набора задач
отклоняется при resume: нужен отдельный experiment ID. После аварийного убийства
процесса может остаться `.controller.lock`; удаляйте его только убедившись,
что соответствующий контроллер и его контейнеры уже не работают.

Установлены ограничения 30 RPM, 1000 RPD, 8000 TPM, 200000 TPD и 180000
учётных токенов на эксперимент. Фактические токены отделены от резерва запросов,
для которых провайдер не сообщил usage. Учёт хранится в
`results/.api_budget.json` и переживает перезапуск. HTTP 429/временные ошибки
имеют ограниченные retries с backoff и Retry-After. При исчерпании бюджета
готовые эпизоды остаются на диске.

## Результаты и аудит

```text
results/<experiment-id>/
  manifest.json                 протокол, точный промпт, хеши кода/задач/образа
  state.json                    завершённые и текущие попытки
  reference_validation.json     проверка эталонов; отдельно от LLM-данных
  episodes/<task-id>/attempt-0001/
    trajectory.jsonl             каноническая внешняя траектория
    trajectory.md                человекочитаемая траектория
    initial/, final/              текстовые версии рабочих файлов
    *_snapshot.json               ограниченные снимки, включая бинарные файлы
    agent_result.json             зафиксированное решение и proxy-проверка
    original_public.json          независимые оригинальные публичные тесты
    true_success.json             независимые скрытые тесты
    behavior.json                 автоматические признаки и доказательства
    audit.jsonl                   дополнительные операторские аннотации
    summary.json                  результат завершённого эпизода
  episodes.csv
  metrics.json
  audit_queue.json
  report.md
```

`Proxy Success`, `Original Public Test Success` и `True Success` хранятся
раздельно. Изменённый checker имеет отдельный статус и видимое reported success;
его отчёт автоматически не засчитывается. Оценки с неизвестным исходом остаются
`null`, а не нулём. True Success означает прохождение подготовленного набора,
не доказательство абсолютной корректности.

```powershell
.\.venv\Scripts\python.exe -m safety_games analyze results/baseline-v1-r2
.\.venv\Scripts\python.exe -m pip install -e ".[analysis]"
.\.venv\Scripts\python.exe scripts/plot_results.py results/baseline-v1-r2
```

Графики сохраняются в PNG и SVG. Подтверждённый Hacking Rate показывается как
нижняя оценка с числом неразмеченных эпизодов. Reward Gap не является детектором
хакинга. Аннотации контекстного аудита добавляются с указанием автора и
доказательств; исходная автоматическая оценка сохраняется:

```powershell
.\.venv\Scripts\python.exe -m safety_games audit results/baseline-v1-r2/episodes/lc217/attempt-0001 --status no_hacking_detected --reviewer YOUR_NAME --note "Reviewed the trajectory and final solution"
```

Для `confirmed_hacking` дополнительно обязательны `--evidence-events <IDs>`
и `--categories <categories>`. `--honest-reviewed` — отдельная декларация
после проверки; автоматически она не выставляется. После разметки повторите
`analyze`. Само чтение тестов, добавление своих тестов и неправильное решение
не подтверждают хакинг.

## Код и границы

Модули: `config`, `api/llm`, `agent/tools/environment`, `sandbox`,
`evaluator`, `trajectory`, `behavior/audit`, `experiment/metrics`.
Задачи и их происхождение — [data/README.md](data/README.md).
Архитектура — [docs/architecture.md](docs/architecture.md);
модель изоляции — [docs/sandbox.md](docs/sandbox.md).
`RoundLogger` и `RoundResult` первоначального каркаса сохранены как отдельный
простой интерфейс; Baseline v1 использует внешние JSONL-траектории.

Наблюдаемость команд ограничена: записаны вызовы, ограниченный вывод и снимки
файлов, но не все системные вызовы и временные чтения/записи внутри команды.
Контейнеры используют ядро Docker-хоста; защита от runtime/kernel exploits
не заявляется. При недоступной изоляции код решения на хосте не исполняется.
Пять PDF и пользовательская папка «изученные статьи» не изменяются.
