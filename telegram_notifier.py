import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime


LOGGER = logging.getLogger(__name__)
MAX_ERROR_LINES = 10
MAX_ERROR_TEXT_LENGTH = 220


@dataclass
class UsageReport:
    user: str
    action: str
    total_records: int
    success_records: int
    error_records: int
    errors: list[str] = field(default_factory=list)
    source: str | None = None


def build_usage_message(report: UsageReport) -> str:
    lines = [
        "Tik Crawler usage",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"User: {report.user}",
        f"Action: {report.action}",
    ]
    if report.source:
        lines.append(f"Source: {report.source}")

    lines.extend(
        [
            f"Total records: {report.total_records}",
            f"Success: {report.success_records}",
            f"Errors: {report.error_records}",
        ]
    )

    if report.errors:
        lines.append("Error details:")
        for error in _compact_errors(report.errors):
            lines.append(f"- {error}")

    public_url = os.getenv("APP_PUBLIC_URL")
    if public_url:
        lines.append(f"App: {public_url}")

    return "\n".join(lines)


def send_usage_notification(report: UsageReport) -> bool:
    return send_telegram_message(build_usage_message(report))


def send_telegram_message(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = float(os.getenv("TELEGRAM_TIMEOUT_SECONDS", "5"))

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        LOGGER.warning("Telegram notification failed: %s", exc)
        return False


def _compact_errors(errors: list[str]) -> list[str]:
    compacted: list[str] = []
    seen: set[str] = set()
    for error in errors:
        text = " ".join(str(error or "Unknown error").split())
        if len(text) > MAX_ERROR_TEXT_LENGTH:
            text = text[: MAX_ERROR_TEXT_LENGTH - 1] + "..."
        if text in seen:
            continue
        seen.add(text)
        compacted.append(text)
        if len(compacted) >= MAX_ERROR_LINES:
            remaining = len({str(item) for item in errors}) - len(compacted)
            if remaining > 0:
                compacted.append(f"...and {remaining} more unique errors")
            break
    return compacted
