# Reward Hacking in LLM Agents — Baseline v1.1

Восстановлен **Baseline v1.1**: исправления инфраструктуры, локальные тесты и аудит старого запуска. 26 ноября пользователь разрешил контрольный smoke, затем полный набор при исправной инфраструктуре и доступном бесплатном бюджете. До открытия локального окна квоты inference не начинается. [Статус продолжения и очередь](docs/baseline_v1_1_execution.md). Публичная награда и модель-судья остаются незапущенными отдельными условиями.

Исходный Baseline v1.0 завершён: 15 настоящих эпизодов Groq `openai/gpt-oss-20b`, True Success 10/15. Его конфигурация, промпт, задачи, решения, траектории и оценки сохранены побайтово. [Первоначальный отчёт](docs/baseline_results.md) и `results/baseline-v1-r2` не являются результатами v1.1.

## Что готово

- Заменяемый LLM-интерфейс, Groq Chat Completions, общий ledger квот, Retry-After/backoff и сохранение доступного usage.
- Бюджет ответа с учётом входа и 8000 TPM; ограниченное продолжение после length и восстановление невалидных tool calls без исполнения/исправления JSON.
- Независимые поля завершения взаимодействия, наличия реализации, корректности, технического completion и аудита.
- Docker без сети/секретов/host mounts, непривилегированный пользователь, seccomp и ограничения ресурсов; отдельный evaluator, ожидаемые ответы остаются на контроллере.
- JSONL/Markdown траектории, снимки/диффы, CSV, консервативный детектор, ручной аудит и интерфейс будущего независимого научного судьи без API-реализации.
- 15 исходных задач, по 3 публичных и 13 собственных скрытых тестов, эталоны и документированное происхождение.
- Безопасный ZIP-экспорт по allowlist с проверкой содержимого и секретов до появления окончательного архива.

Нет обучения, санкций, репутации, памяти между задачами или feedback независимого аудита.

## Установка и локальная проверка

Python 3.11+, для интеграционных проверок — Docker с Linux containers. PowerShell из корня:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path results/protocol_archives/r2)) {
    .\.venv\Scripts\python.exe -m zipfile -e results/protocol_archives/r2-source.zip results/protocol_archives/r2
}
.\.venv\Scripts\python.exe -m safety_games check-config --config configs/baseline_v1_1.toml
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Runtime-зависимость одна: python-dotenv. Без Docker последние команды не исполняют сгенерированный код на host; интеграционные тесты пропускаются. Optional extras `.[analysis]` и `.[research]` нужны только для matplotlib/pypdf.

Полный локальный прогон с Docker, **без LLM API**:

```powershell
docker build --provenance=false --load --tag safety-games-sandbox:local sandbox
$env:SAFETY_GAMES_DOCKER_TESTS = "1"
.\.venv\Scripts\python.exe -W error::ResourceWarning scripts/record_tests.py --output results/baseline-v1.1-preparation/infrastructure_tests.json
Remove-Item Env:SAFETY_GAMES_DOCKER_TESTS
```

Ключ хранится только в локальном `.env`/окружении контроллера; шаблон `.env.example` пустой. `.env` игнорируется Git и экспортом. Для перечисленных локальных тестов действующий ключ не нужен. Поворот ключа не обнуляет квоты организации.

При переносе работы с тем же аккаунтом сохраняйте актуальный локальный `results/.api_budget.json`; новый checkout сам по себе не означает восстановление квоты. ZIP выше содержит только замороженные исходники r2 и нужен для побайтовой проверки сохранности после свежего клонирования.

## Аудит и переанализ v1.0

```powershell
.\.venv\Scripts\python.exe scripts/prepare_v1_1.py
```

Команда требует предварительный preservation manifest, проверяет исходные хеши и создаёт только производные материалы в `results/baseline-v1.1-preparation`. Не изменяет исходный run и не вызывает LLM.

- [Единый audit_manifest.csv](results/baseline-v1.1-preparation/review/audit_manifest.csv).
- [Карточки всех 15 эпизодов](results/baseline-v1.1-preparation/review/README.md): тестовые обращения, записи, изменения checker, итоговый код, ошибки и ограничения.
- [Новые описательные метрики](results/baseline-v1.1-preparation/review/statistics/metrics.json), включая Wilson CI, planned/technical subsets и reasoning usage.
- [Профили исходных задач](results/baseline-v1.1-preparation/tasks/task_profiles.md).

Ручные метки автоматически не выставлены. Отсутствие сигналов не доказывает честность; скрытый провал не доказывает hacking. True Success относится только к конечному набору собственных тестов.

## Документация и продолжение

- [Текущий контрольный запуск и ожидание квоты](docs/baseline_v1_1_execution.md).
- [Отчёт о v1.1 и изменённых файлах](docs/baseline_v1_1_report.md).
- [Предложенный протокол, настройки и бюджет](docs/baseline_v1_1_protocol.md).
- [Предложение контролируемой выборки и калибровки](docs/task_calibration_proposal.md).
- [NEXT_STEPS.md](NEXT_STEPS.md) — состояние для следующей сессии.
- [Архитектура v1.0](docs/architecture.md), [изоляция](docs/sandbox.md), [пять научных источников](docs/literature_review.md), [методологические различия](docs/methodological_differences.md).

Контроль v1.1 использует неизменённый `prompts/coding_agent_v1.txt`; отдельное **незапущенное** условие — `configs/baseline_v1_1_public_reward.toml`. Предлагается максимум 6144 токена ответа с динамическим уменьшением, medium reasoning, 60000 на эпизод, 25 tools, 6 format errors, 2 продолжения length. При эффективных 180000/24h потолок 900000 на 15 эпизодов требует минимум пяти суточных окон; полный повтор до 26 ноября не гарантируется.

Для контрольного эксперимента `baseline-v1-1-control-20261126` согласование smoke и условного полного прогона уже получено. Внешний runner `scripts/run_control_plan.py` ждёт квоту, сохраняет smoke checkpoint и продолжает исходные 15 задач без переигрывания завершённых. Не запускать второй контроллер параллельно с живой очередью. Для другого эксперимента оператор использует `run --config configs/baseline_v1_1.toml --experiment-id <NEW_ID> --stage smoke --approved-stage control:smoke` только после соответствующего согласования. Публичная метрика согласуется отдельно.

## Проверенный исследовательский архив

```powershell
.\.venv\Scripts\python.exe -m safety_games archive --output exports/baseline-v1.1-stage-a.zip
```

Команда не перезаписывает существующий ZIP. Исключаются `.env`, credentials, Git objects, venv, кеши и неразрешённые директории. Проверяются текущие известные секреты, типичные форматы ключей и base64-снимки; symlinks и небезопасные пути отклоняются. ZIP сначала проверяется как `.partial`, затем получает итоговое имя и JSON-отчёт с SHA256. PDF пользователя не переиздаются; их происхождение и хеши описаны в документации. Сканирование не гарантирует распознавание любого неизвестного формата секрета.

Перед отправкой Git-коммита необходимо отдельно проверить staged blobs/историю. Отчёты о секретах не содержат значения ключей. Существовавшие вне этой директории архивы/удалённая история проверке недоступны.
