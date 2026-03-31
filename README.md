# Meeting Notes Bot

Python-сервер на FastAPI, который принимает webhook от Read AI после 1:1 встречи, прогоняет транскрипт через LLM и создаёт карточку в Notion базе `1:1 Management`.

## Что умеет

- `POST /webhook/readai` принимает webhook от Read AI и проверяет подпись `X-Read-Signature`
- `POST /webhook/test` позволяет отправлять тестовый payload без подписи
- `GET /health` возвращает статус сервиса
- Из payload извлекаются `participants`, `transcript`, `summary`
- Страница в Notion создаётся только для встреч формата `1:1`; остальные webhook'и пропускаются со статусом `skipped`
- Если в webhook Read AI никто из участников не найден в `TEAM_MAPPING`, запрос тоже завершается со статусом `skipped`, чтобы тестовые payload'ы Read AI проходили с `2xx`
- Транскрипт и саммари отправляются в LLM через LiteLLM gateway
- По `TEAM_MAPPING` определяется репорт и создаётся страница в базе Notion `1:1 Management`

## Структура

```text
meeting-notes-bot/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   └── services/
│       ├── llm.py
│       ├── notion.py
│       └── readai.py
├── .env.example
├── requirements.txt
└── README.md
```

## Быстрый старт

```bash
cd meeting-notes-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

После запуска сервис будет доступен на `http://127.0.0.1:8000`.

## Deploy on Render

Проект подготовлен для деплоя на Render через [`render.yaml`](render.yaml).

1. Запушьте актуальный код в GitHub.
2. Откройте Render и создайте новый Blueprint или Web Service из этого репозитория.
3. Если создаёте сервис вручную, используйте:
   - Runtime: `Python`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health Check Path: `/health`
4. Добавьте переменные окружения из `.env.example` в Render dashboard:
   - `NOTION_TOKEN`
   - `NOTION_11_DATABASE_ID`
   - `NOTION_REPORTS_DATABASE_ID`
   - `LLM_BASE_URL`
   - `LLM_API_KEY`
   - `LLM_MODEL`
   - `READAI_WEBHOOK_SECRET`
   - `READAI_SKIP_SIGNATURE_VERIFICATION`
   - `TEAM_MAPPING`
5. После успешного деплоя получите публичный URL сервиса:
   - health check: `https://<your-service>.onrender.com/health`
   - Read AI webhook: `https://<your-service>.onrender.com/webhook/readai`
   - test webhook: `https://<your-service>.onrender.com/webhook/test`

Перед подключением Read AI проверьте `POST /webhook/test`, чтобы убедиться, что Notion и LLM credentials работают корректно.

## Переменные окружения

Пример лежит в `.env.example`:

```env
NOTION_TOKEN=
NOTION_11_DATABASE_ID=
NOTION_REPORTS_DATABASE_ID=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
READAI_WEBHOOK_SECRET=
READAI_SKIP_SIGNATURE_VERIFICATION=false
TEAM_MAPPING={"participant_a":"notion_page_id","participant_b":"notion_page_id","participant_c":"notion_page_id"}
```

Назначение:

- `NOTION_TOKEN` - токен internal integration в Notion
- `NOTION_11_DATABASE_ID` - ID базы `1:1 Management`
- `NOTION_REPORTS_DATABASE_ID` - ID базы `Reports` для будущих этапов; в текущей версии не используется напрямую, но хранится в конфиге
- `LLM_BASE_URL` - base URL LiteLLM gateway, например `https://your-litellm-host/v1`
- `LLM_API_KEY` - ключ для LiteLLM gateway
- `LLM_MODEL` - модель, которую gateway должен вызвать
- `READAI_WEBHOOK_SECRET` - `signing key` из настроек webhook в Read AI; если он в base64, сервис сам его декодирует
- `READAI_SKIP_SIGNATURE_VERIFICATION` - временный bypass для первичной настройки webhook; в production должен быть `false`
- `TEAM_MAPPING` - JSON-объект `имя -> Notion page ID` для репортов

## Настройка Notion integration

1. Создайте internal integration в Notion:
   - Откройте `https://www.notion.so/profile/integrations`
   - Нажмите `New integration`
   - Скопируйте `Internal Integration Token` в `NOTION_TOKEN`
2. Дайте интеграции доступ к базам:
   - Откройте базу `1:1 Management`
   - Нажмите `...` -> `Connections` -> добавьте вашу integration
   - Повторите то же для базы `Reports`
3. Проверьте названия свойств в базе `1:1 Management`:
   - `Title` с типом `Title`
   - `Date` с типом `Date`
   - `Report` с типом `Relation`
4. Получите `database_id`:
   - Откройте базу в браузере
   - В URL будет длинный идентификатор из 32 символов перед `?v=...`
   - Это и есть `NOTION_11_DATABASE_ID` или `NOTION_REPORTS_DATABASE_ID`
5. Получите `page_id` для каждого репорта:
   - Откройте карточку сотрудника в базе `Reports`
   - Скопируйте ссылку на страницу
   - Последний длинный идентификатор в URL страницы и есть `page_id`
   - Заполните `TEAM_MAPPING`

## Настройка Read AI webhook

Настройте webhook Read AI на endpoint:

```text
POST /webhook/readai
```

Сервис ожидает:

- header `X-Read-Signature`
- JSON body с данными встречи

Подпись проверяется как HMAC SHA-256 от raw body с `READAI_WEBHOOK_SECRET`. Если Read AI выдаёт signing key в base64, сервис сначала декодирует его и затем проверяет подпись.

Если вы ещё не получили signing key и Read AI не даёт сохранить webhook из-за `401`, можно временно выставить `READAI_SKIP_SIGNATURE_VERIFICATION=true`, создать webhook, скопировать signing key из Read AI, затем записать его в `READAI_WEBHOOK_SECRET`, вернуть `READAI_SKIP_SIGNATURE_VERIFICATION=false` и сделать redeploy.

Поддерживаются типовые поля payload:

- `participants`
- `transcript`
- `summary`
- `action_items`
- `chapter_summaries`
- `start_time`, `started_at`, `scheduled_at`, `date`, `created_at`

Если конкретная структура Read AI окажется чуть другой, парсер в `app/services/readai.py` можно быстро расширить под фактический payload.

## Тестирование без Read AI

Пример запроса на тестовый endpoint:

```bash
curl -X POST http://127.0.0.1:8000/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "participants": [
      {"name": "Participant A"},
      {"name": "Participant B"}
    ],
    "summary": "Обсудили статус проектов и планы на квартал.",
    "transcript": "Participant A: Как дела по проекту? Participant B: Основной риск закрываем к пятнице.",
    "start_time": "2026-03-31T09:00:00Z"
  }'
```

Ожидаемый результат:

- сервис определит репорта по `TEAM_MAPPING`
- вызовет LLM
- создаст новую страницу в `1:1 Management`
- вернёт `notion_page_id` и `notion_url`

## Что создаётся в Notion

Сервис создаёт новую страницу в базе `1:1 Management`:

- `Title`: `1:1 with {имя}`
- `Date`: дата встречи
- `Report`: relation на страницу репорта

В body страницы добавляются секции:

- `Summary`
- `Topics`
- `Decisions`

## Логи

Логирование сделано через `structlog` в JSON-формате. Основные события:

- получение webhook
- ошибки валидации payload
- ошибки вызова LLM
- ошибки создания страницы в Notion
- успешная обработка webhook

## Ограничения текущего этапа

- Используется только создание карточки 1:1
- `NOTION_REPORTS_DATABASE_ID` пока не задействован в логике поиска репорта
- Определение репорта идёт только через `TEAM_MAPPING`, без запроса в базу `Reports`
