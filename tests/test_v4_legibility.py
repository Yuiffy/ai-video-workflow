"""Catch unstyled dark SVG text in the V4 explainer before encoding."""
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright


class V4LegibilityTest(unittest.TestCase):
    def test_each_slide_has_no_dark_text_on_dark_canvas(self):
        html = Path(__file__).resolve().parents[1] / 'projects/development-history-v4-pagewise/ppt/index.html'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                page.goto(html.as_uri())
                for index in range(page.locator('[data-slide]').count()):
                    page.evaluate('i => window.renderAt({slide:i,time:999,duration:30})', index)
                    dark = page.locator(f'[data-slide="{index}"]').evaluate('section => [...section.querySelectorAll("text")].filter(text => { const fill = getComputedStyle(text).fill; return ["rgb(0, 0, 0)", "rgb(7, 18, 25)", "rgb(16, 42, 50)"].includes(fill) && text.textContent.trim() !== "?" }).map(text => text.textContent.trim())')
                    self.assertEqual(dark, [], f'slide {index + 1} has dark text')
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
