from __future__ import annotations

import asyncio
from pathlib import Path


async def record_ppt(html: Path, output: Path, seconds_per_slide: int = 7, viewport: tuple[int, int] = (1920, 1080), fps: int = 30) -> Path:
    from playwright.async_api import async_playwright
    output.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, device_scale_factor=1, record_video_dir=str(output.parent / "recordings"), record_video_size={"width": viewport[0], "height": viewport[1]})
        page = await context.new_page()
        await page.goto(html.resolve().as_uri(), wait_until="networkidle")
        await page.evaluate("window.startRecording && window.startRecording()")
        slides = await page.locator("[data-slide]").count()
        await page.wait_for_timeout(max(1, slides) * seconds_per_slide * 1000)
        video = page.video
        await context.close()
        await browser.close()
        if video is None:
            raise RuntimeError("Playwright 没有产生录制文件")
        recorded = Path(await video.path())
        output = output.with_suffix(".webm")
        recorded.replace(output)
    return output


def record_ppt_sync(*args, **kwargs) -> Path:
    return asyncio.run(record_ppt(*args, **kwargs))
