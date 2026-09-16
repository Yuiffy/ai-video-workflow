"""The explainer must move reproducibly when recording or seeking the frame clock."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from src.ppt_recorder import deck_digest


class DeckTests(unittest.TestCase):
    def test_script_change_invalidates_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html = root/"index.html"
            html.write_text("<script src='motion.js'></script>")
            js = root/"motion.js"
            js.write_text("let time=0")
            before = deck_digest(html)
            js.write_text("let time=1")
            self.assertNotEqual(before, deck_digest(html))

    def test_v2_diagrams_animate_and_seek_deterministically(self):
        from playwright.sync_api import sync_playwright
        html = Path(__file__).resolve().parents[1]/"projects/development-history-v2/ppt/index.html"
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 640, "height": 360})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(html.as_uri())
                page.evaluate("document.fonts.ready")
                count = page.locator("[data-slide]").count()
                self.assertEqual(count, 16)
                for index in range(count):
                    def frame(t):
                        page.evaluate("v=>window.renderAt(v)", {"slide": index, "time": t, "duration": 15})
                        pixels = hashlib.sha256(page.screenshot()).hexdigest()
                        layout = page.evaluate("""Array.from(document.querySelectorAll('.slide.active *')).map(e=>{
                            const c=getComputedStyle(e),r=e.getBoundingClientRect();
                            return [e.textContent,c.opacity,c.transform,c.clipPath,c.strokeDashoffset,r.x,r.y,r.width,r.height]
                        })""")
                        return pixels, layout
                    first = frame(1)
                    later = frame(11)
                    self.assertNotEqual(first[0], later[0], f"Slide {index+1} is visually static")
                    self.assertNotEqual(first[1], later[1], f"Slide {index+1} has no animated layout")
                    # GPU text antialiasing may vary by 1–2 color levels after seeking.
                    self.assertEqual(first[1], frame(1)[1], f"Slide {index+1} cannot seek reliably")
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
