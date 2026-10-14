"""Render and inspect the authored 5.6-second sticker opening."""
from pathlib import Path
import argparse
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
# The existing local inspect.py must not shadow Python's standard inspect module.
sys.path = [str(ROOT)] + [entry for entry in sys.path if Path(entry).resolve() != Path(__file__).resolve().parent]

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from src.ppt_recorder import record_scene

OUT = ROOT / "outputs/sui-suddenly-life-20261012"
HTML = OUT / "sticker-intro/index.html"
QA = OUT / "sticker-intro/qa"
QA.mkdir(parents=True,exist_ok=True)
shutil.copyfile(Path(__file__).with_name("intro.html"),HTML)
shutil.copyfile(OUT/"intro_room.jpg",HTML.parent/"assets/room.jpg")
parser=argparse.ArgumentParser()
parser.add_argument("--preview-only",action="store_true")
args=parser.parse_args()
beats=[0,1.65,1.99,2.20,2.55,3.04,3.28,3.65,3.99,4.07,4.20,5.40]
report={"duration":5.6,"fps":30,"frames":168,"beats":[],"errors":[]}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1280,"height":720},device_scale_factor=1)
    page.on("pageerror",lambda error:report["errors"].append(str(error)))
    page.goto(HTML.as_uri()+"?capture=1",wait_until="load")
    page.wait_for_function("[...document.images].every(image => image.complete && image.naturalWidth > 0)")
    sheet=Image.new("RGB",(1600,3*249),"#18151f")
    draw=ImageDraw.Draw(sheet)
    cookie_boxes=[]
    for i,t in enumerate(beats):
        state=page.evaluate("time => window.renderAt({time})",t)
        cookie_boxes.append(page.locator("#cookie").bounding_box())
        image_path=QA/f"beat-{t:.2f}.png"
        page.screenshot(path=str(image_path))
        picture=Image.open(image_path).convert("RGB").resize((400,225))
        x=(i%4)*400;y=(i//4)*249
        sheet.paste(picture,(x,y+24));draw.text((x+10,y+7),f"{t:.2f} s",fill="white")
        report["beats"].append({"time":t,"frame":str(image_path),"state":state})
    report["cookie_position_fixed"] = all(box==cookie_boxes[0] for box in cookie_boxes)
    assert report["cookie_position_fixed"]
    assert not report["errors"],report["errors"]
    sheet.save(QA/"storyboard.jpg",quality=94)
    if not args.preview_only:
        config={"recording":{"fps":30,"viewport":{"width":1280,"height":720}},"render":{"preset":"fast"}}
        record_scene(page,0,5.6,OUT/"intro_stickers-raw.mp4",config)
        report["rendered_file"]=str(OUT/"intro_stickers-raw.mp4")
    browser.close()
(QA/"render-qa.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"frames":168,"cookie_position_fixed":True,"errors":report["errors"],"storyboard":str(QA/"storyboard.jpg")},ensure_ascii=False))
