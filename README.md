# TikTok Stats Internal Tool

Small internal web tool for exporting public TikTok video stats from pasted links or uploaded files.

## Paste link mode

Paste one or many TikTok video URLs. Separate links by new lines or commas.

The app exports a file with these columns:

- `Url`
- `Caption`
- `View`
- `Like`
- `Comment`
- `Share`
- `Save`

## Input

Upload a file containing TikTok video URLs.

The app auto-detects URL columns named:

- `url`
- `link`
- `tiktok_url`
- `tiktok_link`
- `video_url`

If there is no header row, the first column containing TikTok URLs is used.

## Output columns

The downloaded file uses the same output columns for both pasted links and uploaded files:

- `Url`
- `Caption`
- `View`
- `Like`
- `Comment`
- `Share`
- `Save`

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
uvicorn web_app:app --reload
```

Open `http://127.0.0.1:8000`.

## Environment variables

```bash
export MS_TOKEN="your_tiktok_ms_token"
export INTERNAL_TOOL_USER="admin"
export INTERNAL_TOOL_PASSWORD="change-me"
export MAX_BATCH_ROWS="100"
export MAX_UPLOAD_MB="10"
export APP_PUBLIC_URL="https://tik-crawler.minhat.online"
export TELEGRAM_BOT_TOKEN="123456:bot-token"
export TELEGRAM_CHAT_ID="-1001234567890"
export TELEGRAM_TIMEOUT_SECONDS="5"
```

`MS_TOKEN` is optional, but TikTok scraping is usually more reliable with it.

Telegram notifications are optional. If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID`
is missing, the app skips notifications and continues processing normally.

## CLI

```bash
python main.py "https://www.tiktok.com/@user/video/123"
```

## Docker

```bash
docker build -t tiktok-stats .
docker run --rm -p 8000:8000 \
  -e INTERNAL_TOOL_PASSWORD="change-me" \
  -e MS_TOKEN="your_tiktok_ms_token" \
  tiktok-stats
```

Open `http://localhost:8000`.

## Deployment notes

Docker on a VPS is the most practical deployment path because the app depends on Playwright and a real browser runtime.

Vercel serverless is not recommended for this app: browser binaries are large, cold starts are slow, and TikTok requests may take longer than typical serverless limits. If you want a managed platform, prefer a container-capable service such as Render, Fly.io, Railway, or a VPS.
