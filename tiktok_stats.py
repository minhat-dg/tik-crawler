import asyncio
import errno
import os
from datetime import datetime, timezone
from typing import Any

from TikTokApi import TikTokApi


DEFAULT_BROWSER = "chromium"
CHROMIUM_ARGS = [
    "--mute-audio",
    "--autoplay-policy=user-gesture-required",
    "--disable-crash-reporter",
    "--disable-crashpad",
    "--disable-dev-shm-usage",
    "--no-first-run",
]


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def pick_stats(info: dict[str, Any]) -> dict[str, Any]:
    stats = info.get("statsV2") or info.get("stats")
    if not isinstance(stats, dict):
        return {}
    return stats


def normalize_video_info(
    *,
    url: str,
    video_id: str | None,
    info: dict[str, Any],
) -> dict[str, Any]:
    stats = pick_stats(info)
    author = info.get("author") or {}
    if not isinstance(author, dict):
        author = {"uniqueId": author}

    return {
        "url": url,
        "id": info.get("id") or video_id,
        "author": author.get("uniqueId") or author.get("nickname"),
        "description": info.get("desc"),
        "create_time": to_int(info.get("createTime")),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "view": to_int(stats.get("playCount")),
            "like": to_int(stats.get("diggCount")),
            "comment": to_int(stats.get("commentCount")),
            "share": to_int(stats.get("shareCount")),
            "collect": to_int(stats.get("collectCount")),
        },
        "raw_stats": stats,
    }


async def fetch_video_data(
    url: str,
    *,
    browser: str = DEFAULT_BROWSER,
    headless: bool = True,
) -> dict[str, Any]:
    results = await fetch_many_video_data([url], browser=browser, headless=headless)
    result = results[0]
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result["data"]


async def fetch_many_video_data(
    urls: list[str],
    *,
    browser: str = DEFAULT_BROWSER,
    headless: bool = True,
    sleep_after: int = 3,
    delay_between_urls: float = 0,
) -> list[dict[str, Any]]:
    ms_token = os.getenv("ms_token") or os.getenv("MS_TOKEN")
    results: list[dict[str, Any]] = []
    browser_args = CHROMIUM_ARGS.copy() if browser == "chromium" else None
    launch_headless = headless
    if browser == "chromium" and headless:
        browser_args = ["--headless=new", *CHROMIUM_ARGS]
        launch_headless = False

    api = TikTokApi()
    try:
        try:
            await api.create_sessions(
                ms_tokens=[ms_token] if ms_token else None,
                num_sessions=1,
                sleep_after=sleep_after,
                browser=browser,
                headless=launch_headless,
                override_browser_args=browser_args,
                suppress_resource_load_types=["media"],
            )
        except Exception as exc:
            return [
                {
                    "url": url,
                    "data": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                for url in urls
            ]

        for index, url in enumerate(urls):
            if delay_between_urls and index > 0:
                await asyncio.sleep(delay_between_urls)

            try:
                video = api.video(url=url)
                info = await video.info()
                results.append(
                    {
                        "url": url,
                        "data": normalize_video_info(
                            url=url,
                            video_id=video.id,
                            info=info,
                        ),
                        "error": None,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "url": url,
                        "data": None,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        return results
    finally:
        await close_tiktok_api(api)


async def close_tiktok_api(api: TikTokApi) -> None:
    try:
        await api.close_sessions()
    except Exception:
        try:
            await api.stop_playwright()
        except Exception:
            pass
    finally:
        reap_child_processes()


def reap_child_processes() -> int:
    if os.name != "posix":
        return 0

    reaped = 0
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        except OSError as exc:
            if exc.errno == errno.ECHILD:
                break
            raise

        if pid == 0:
            break
        reaped += 1

    return reaped
