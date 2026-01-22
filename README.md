# QB Shop (Telegram WebApp + Bot)

Telegram-магазин iPhone на базе парсера `syoma.py`. Каталог и цены берутся с SyomaStore, картинки скачиваются один раз и используются локально.

## Быстрый старт

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy config.example.env .env
```

Заполни `.env`:
- `BOT_TOKEN`
- `ADMIN_CHAT_ID`
- `WEBAPP_URL` (ссылка на GitHub Pages)

## Обновление каталога

```powershell
.\.venv\Scripts\python scripts\export_store_catalog.py
```

Файл каталога: `public/products.json`  
Картинки: `public/assets/products/`

При повторном запуске изображения не скачиваются заново, если файл уже есть.

## Запуск бота

```powershell
.\.venv\Scripts\python bot.py
```

Команды:
- `/start` — кнопка открытия магазина
- `/id` — показывает chat id

## WebApp

Статика находится в `public/`. GitHub Pages раздает именно эту папку:
- `public/index.html`
- `public/app.js`
- `public/style.css`
- `public/products.json`
- `public/assets/products/*`

## Автообновление и Pages

Workflow: `.github/workflows/update_and_deploy.yml`  
Запускается раз в час и публикует `public/` в ветку `gh-pages`.

Включи Pages:
1. Settings → Pages
2. Branch: `gh-pages` / `/ (root)`
3. Сохрани и возьми URL сайта

Actions будут обновлять:
- `public/products.json`
- `public/assets/products/*` (кэш картинок)

## Переменные окружения

Смотри `config.example.env`.
