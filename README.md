# M5 Range Scanner

Веб-сканер Bybit USDT perpetual futures для поиска M5-диапазонов, поджатий и потенциальных пробоев.

## Что реализовано

- FastAPI backend с `POST /api/scan`.
- Bybit V5 endpoints:
  - `/v5/market/instruments-info` с пагинацией;
  - `/v5/market/tickers`;
  - `/v5/market/kline`.
- Фильтрация только по futures-спецификации и turnover:
  - `status == Trading`;
  - `contractType == LinearPerpetual`;
  - `quoteCoin == USDT`;
  - `turnover_24h_usd >= 2_000_000`.
- Blacklist отсутствует.
- Spread стакана не используется.
- React UI:
  - кнопка `Сканировать`;
  - sortable table;
  - кликабельный тикер на Bybit;
  - rating, 24h turnover, price position, direction, status, class, flat quality, volume ratio, range width;
  - кнопка `Свой график` с inline SVG-свечами, support/resistance, прямоугольником диапазона и зоной предшествующего тренда;
  - раскрытие строки с уровнями, R2, ADX, slope, inside ratios, reasons и warnings.

## Логика флэта

Сканер валидирует базовую форму горизонтального флэта через hard filters:

- `flat_range_pct <= 2.0`;
- `abs(flat_slope_rel) <= 0.003`;
- `flat_r_squared <= 0.45`;
- `close_inside_ratio >= 0.75`.

Остальные признаки не удаляют setup сразу, а влияют на rating и warnings:

- `adx_14`;
- `body_inside_ratio`;
- `false_breakouts`;
- независимые касания уровней;
- `sideways_confidence`.

Направление setup разрешается только по предшествующему тренду:

- bullish / neutral-bullish + цена у resistance -> `LONG`;
- bearish / neutral-bearish + цена у support -> `SHORT`;
- противоположные случаи получают `trend_mismatch` и скрываются при обычном `min_rating=70`.

## Запуск

Через Docker Compose:

```bash
docker compose up --build
```

Открыть:

```text
http://localhost:5173
```

Локально без Docker:

Установить Python-зависимости:

```bash
python3 -m pip install -r requirements.txt pytest
```

Установить frontend-зависимости:

```bash
npm install
```

Запустить backend:

```bash
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Запустить frontend:

```bash
npm run dev
```

Открыть:

```text
http://localhost:5173
```

## Тесты

```bash
pytest
npm run build
```

## Важные ограничения

- Это не торговый бот.
- Сканер не открывает сделки, не считает плечо и размер позиции.
- Рейтинг является эвристикой, а не вероятностью успеха.
- Следующие этапы: PostgreSQL, история scan/setup, outcome tracking через 15/30/60 минут и статистика.
