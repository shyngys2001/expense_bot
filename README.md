# Smart Budget Tracker (MVP)

MVP для личного учета доходов и расходов с быстрым вводом, автокатегоризацией, месячным отчетом и графиком.

## Стек

- Python 3.12+
- FastAPI
- PostgreSQL
- SQLAlchemy 2.0 (async) + asyncpg
- Alembic
- Jinja2 + Chart.js (CDN)
- Docker Compose

## Структура

- `/app` — backend и шаблоны UI
- `/alembic` — миграции
- `/tests` — тесты
- `docker-compose.yml` — сервисы `api` + `db`

## Быстрый старт

1. Скопировать конфиг (если нужно):

```bash
cp .env.example .env
```

2. Запустить:

```bash
docker compose up --build
```

3. Открыть приложение:

- [http://localhost:8000](http://localhost:8000)
- Swagger/OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

## API (MVP)

### Quick add

- `POST /api/quick-add`
- Body: `{ "text": "кофе 1200" }`, `{ "text": "зарплата +500000" }`

Правила парсинга:

- если в тексте есть `+`, тип = `income`, иначе `expense`
- сумма = последнее число в строке
- валюта по умолчанию `KZT`
- описание = текст без суммы
- дата = текущая (server local)

### Transactions

- `GET /api/transactions?month=YYYY-MM`
- `GET /api/transactions?month=YYYY-MM&account_id=1`
- `POST /api/transactions`
- `PATCH /api/transactions/{id}`
- `DELETE /api/transactions/{id}`
- `GET /api/transactions/{id}/debug`

Пример ручной смены категории c lock:

```bash
curl -X PATCH http://localhost:8000/api/transactions/123 \
  -H "Content-Type: application/json" \
  -d '{
    "category_id": 2,
    "category_locked": true
  }'
```

Поведение `PATCH`:

- если передан только `category_id` и категория изменилась, `category_locked` ставится в `true` по умолчанию
- можно явно снять lock через `"category_locked": false`
- можно вручную менять `kind` (`income|expense|transfer`); при ручной смене `match_confidence=100`

`GET /api/transactions/{id}/debug` возвращает технический источник операции:

- `source` (`manual|import_pdf|import_csv|import_xlsx`)
- `import_id` (batch импорта, если есть)
- `account_id`
- `raw`, `external_hash`, `created_at`

### Categories

- `GET /api/categories`
- `GET /api/categories?type=expense`
- `GET /api/categories?type=income`

### Accounts

- `GET /api/accounts`
- `GET /api/accounts/{id}/balance?from=YYYY-MM-DD&to=YYYY-MM-DD&include_pending=false`

По умолчанию создается счет `Основной счет`, который используется для quick-add/импорта, если `account_id` не передан.

Ответ `/api/accounts/{id}/balance`:

- `opening_balance` — начальный остаток из выписки (если найден)
- `calculated_closing_balance` — расчетный остаток по `signed_amount` и только `status=posted`
- `statement_closing_balance` — остаток из шапки выписки
- `diff` — разница между расчетом и остатком в выписке
- `pending_total` — сумма операций `status=pending`
- `available_balance` — остаток с учетом флага `include_pending`
- `warning` — предупреждение (например, если нет начального остатка)

### Rules

- `GET /api/rules?type=expense`
- `POST /api/rules`
- `PATCH /api/rules/{id}`
- `DELETE /api/rules/{id}`
- `POST /api/rules/apply?month=YYYY-MM`

Пример создания правила:

```bash
curl -X POST http://localhost:8000/api/rules \
  -H "Content-Type: application/json" \
  -d '{
    "pattern": "yandex go",
    "match_type": "contains",
    "category_id": 2,
    "priority": 100,
    "is_active": true
  }'
```

Пример массового применения правил за месяц:

```bash
curl -X POST "http://localhost:8000/api/rules/apply?month=2026-02"
```

Важно: транзакции с `category_locked=true` не перезаписываются при `rules/apply`.

### Transfers (auto-pair между счетами)

- `POST /api/transfers/auto-pair`
- `GET /api/transfers/pairs?from=YYYY-MM-DD&to=YYYY-MM-DD`

Пример авто-сверки:

```bash
curl -X POST http://localhost:8000/api/transfers/auto-pair \
  -H "Content-Type: application/json" \
  -d '{
    "from": "2026-02-01",
    "to": "2026-02-28",
    "window_days": 1,
    "tolerance": 0,
    "threshold": 80,
    "account_ids": [1, 2]
  }'
```

Логика:

- ищутся пары `expense` на счете A + `income` на счете B с одинаковой валютой и суммой
- окно дат: `±window_days`
- при `confidence >= threshold` обе транзакции получают `kind=transfer`, `transfer_pair_id`, `matched_account_id`

### Reports

- `GET /api/reports/monthly?month=YYYY-MM`
- `GET /api/reports/monthly?month=YYYY-MM&account_id=1`

Ответ содержит:

- `total_income`
- `total_expense`
- `total_transfers`
- `balance`
- `breakdown_by_category`

Важно: `total_income/total_expense` считаются только по `kind in ('income','expense')`. `transfer` учитывается отдельно в `total_transfers`.

### Import PDF Statement

- `POST /api/import/pdf-statement` (`multipart/form-data`, поля `file`, `account_id`)
- Поддерживаются выписки Kaspi Gold и Freedom Bank.
- `account_id` обязателен.
- Импортируются только строки таблицы операций, без хранения персональных данных из шапки (ИИН/номер карты).
- Дедупликация выполняется по `external_hash`.
- При импорте заполняются `signed_amount`, `kind`, `status`, `account_id`, затем применяется автокатегоризация.
- `status=pending` ставится для операций "в обработке"; такие операции не включаются в posted-остаток и monthly totals.
- В `statement_imports` сохраняются: `period_from/period_to`, `opening_balance`, `closing_balance`, `pending_balance`, `currency`, `account_id`.
- Каждая импортированная транзакция получает `import_id` и `source='import_pdf'`.
- `external_hash` учитывает `account_id`, чтобы операции разных счетов не склеивались.

Откат импорта:

- `POST /api/imports/{import_id}/rollback`
- удаляет только транзакции из указанного batch (`import_id`), ручные операции не затрагиваются.

Извлечение остатков из шапки:

- Kaspi: `opening_balance` и `closing_balance` из строк `Доступно на ...`.
- Freedom: `closing_balance` по валюте (`KZT`/`USD`) и `pending_balance` из строки `Сумма в обработке`.

Ответ:

- `rows_total`
- `inserted`
- `skipped`
- `errors`

## Seed данные

При старте приложения, если таблицы пустые, автоматически создаются:

- категории расходов: `Food`, `Transport`, `Home`, `Health`, `Entertainment`, `Subscriptions`, `Transfers`, `Other`
- категории доходов: `Salary`, `Gift`, `Other`
- базовые правила автокатегоризации (например: `yandex.eda`, `yandex.go`, `ip dzhumagulov`, `netflix`, `magnum`, `minimarket`)

## Тесты

```bash
pytest
```

Покрыты quick-add, PDF-парсер (включая pending и шапку выписки), правила автокатегоризации и сверка переводов.

## Полезные команды

```bash
alembic upgrade head
alembic downgrade -1
```

Применение миграций внутри контейнера:

```bash
docker compose exec api alembic upgrade head
```

## Миграции и сброс dev БД

Если нужно полностью пересоздать базу в dev:

```bash
docker compose down -v
docker compose up --build
```

Повторное применение миграций:

```bash
docker compose exec api alembic upgrade head
```

## Флаги окружения

- `SEED_DEMO=false` — демо-данные не добавляются при старте (по умолчанию выключено).

## Как найти лишнюю операцию

1. Откройте операцию в UI: в карточке есть chip источника (`РУЧНОЕ` или `BANK PDF #id`).
2. Для точной проверки вызовите:
   `GET /api/transactions/{id}/debug`
3. Если `source=manual`, это не импорт из выписки.
4. Если `source=import_pdf`, используйте `import_id` и при необходимости откатите batch:
   `POST /api/imports/{import_id}/rollback`

## Проверка multi-account transfer flow

1. Импортируй выписку первого счета через UI/API с `account_id=1`.
2. Импортируй выписку второго счета с `account_id=2`.
3. Вызови `POST /api/transfers/auto-pair` за нужный период.
4. Проверь `GET /api/transfers/pairs` — пары должны иметь `kind=transfer`.
5. Проверь отчет `GET /api/reports/monthly` — доходы/расходы не должны раздуваться переводами.

## Проверка сверки остатков по выпискам

1. Импортируй Kaspi PDF в нужный счет.
2. Импортируй Freedom PDF во второй счет.
3. Для каждого счета вызови:
   `GET /api/accounts/{id}/balance?from=YYYY-MM-DD&to=YYYY-MM-DD&include_pending=false`
4. Ожидаемо:
   - `diff` близок к `0` для корректно импортированной выписки (допуск 1-2 тг).
   - `pending_total` показывает суммы "в обработке".
5. Если `diff` не ноль, проверь `warning` и список pending операций.
