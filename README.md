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

### Categories

- `GET /api/categories`
- `GET /api/categories?type=expense`
- `GET /api/categories?type=income`

### Accounts

- `GET /api/accounts`

По умолчанию создается счет `Main Account`, который используется для quick-add/импорта, если `account_id` не передан.

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
- Поддерживается выписка Freedom Bank (таблица операций).
- Импортируются только строки таблицы операций, без хранения персональных данных из шапки (ИИН/номер карты).
- Дедупликация выполняется по `external_hash`.
- При импорте сразу заполняются `signed_amount`, `kind`, `account_id`; затем применяется автокатегоризация.

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

Покрыты базовые сценарии парсера quick-add.

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

## Проверка multi-account transfer flow

1. Импортируй выписку первого счета через UI/API с `account_id=1`.
2. Импортируй выписку второго счета с `account_id=2`.
3. Вызови `POST /api/transfers/auto-pair` за нужный период.
4. Проверь `GET /api/transfers/pairs` — пары должны иметь `kind=transfer`.
5. Проверь отчет `GET /api/reports/monthly` — доходы/расходы не должны раздуваться переводами.
