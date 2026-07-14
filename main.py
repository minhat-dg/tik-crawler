import argparse
import asyncio
import json
import os

from tiktok_stats import DEFAULT_BROWSER, fetch_video_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch public TikTok video stats from a video URL."
    )
    parser.add_argument("url", help="TikTok video URL")
    parser.add_argument(
        "--browser",
        default=os.getenv("TIKTOK_BROWSER", DEFAULT_BROWSER),
        choices=("chromium", "firefox", "webkit"),
        help="Playwright browser to use. Default: chromium",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Run Playwright in headed mode. Useful when TikTok blocks headless sessions.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    data = await fetch_video_data(
        args.url,
        browser=args.browser,
        headless=not args.show_browser,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
