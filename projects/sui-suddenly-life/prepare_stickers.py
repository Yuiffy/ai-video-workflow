"""Cut the existing character frames into local sticker assets."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path = [str(ROOT)] + [entry for entry in sys.path if Path(entry).resolve() != Path(__file__).resolve().parent]

import cv2
import numpy as np
from PIL import Image, ImageDraw

OUT = ROOT / "outputs/sui-suddenly-life-20261012"
ASSETS = OUT / "sticker-intro/assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# The mascot outline is a separate plate; it never moves when either prop flies.
cookie = np.asarray(Image.open(OUT / "qa/intro_fixed-first.png").convert("RGB"))
mask = np.zeros(cookie.shape[:2], np.uint8)
outline = np.array([[300,220],[357,208],[420,222],[424,269],[470,308],
                    [510,277],[533,280],[528,313],[501,344],[479,369],
                    [468,427],[435,470],[433,527],[404,530],[399,482],
                    [334,482],[319,518],[299,522],[295,510],[315,471],
                    [270,436],[236,445],[224,431],[236,407],[253,379],
                    [261,328],[280,287],[301,269]], np.int32)
cv2.fillPoly(mask, [outline], cv2.GC_PR_FGD)
cv2.ellipse(mask, (368,370), (88,89), 0, 0, 360, cv2.GC_FGD, -1)
cv2.grabCut(cookie, mask, None, np.zeros((1,65)), np.zeros((1,65)), 4, cv2.GC_INIT_WITH_MASK)
alpha = np.isin(mask, [cv2.GC_FGD, cv2.GC_PR_FGD]).astype(np.uint8) * 255
cv2.fillPoly(alpha,[np.array([[241,420],[264,419],[268,443],[250,447]],np.int32)],0)
Image.fromarray(np.dstack([cookie,alpha])).crop((220,205,540,540)).save(ASSETS / "cookie.png")

source = OUT / "dance_clean-raw.mp4"
for key, seconds in [("sui-front",0),("sui-back",3.7)]:
    frame = ASSETS / (key + "-source.png")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss",str(seconds),
                    "-i",str(source),"-frames:v","1",str(frame)],check=True)
    rgb = np.asarray(Image.open(frame).convert("RGB"))
    # Background cyan is excluded; dark outlines and pale lavender hair stay.
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    background = (hsv[:,:,0] > 65) & (hsv[:,:,0] < 97) & (hsv[:,:,1] > 45) & (hsv[:,:,2] > 135)
    matte = np.where(background, cv2.GC_BGD, cv2.GC_PR_FGD).astype(np.uint8)
    matte[:, :310] = cv2.GC_BGD
    matte[:, 970:] = cv2.GC_BGD
    matte[:25, :] = cv2.GC_BGD
    cv2.grabCut(rgb,matte,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
    a = np.isin(matte,[cv2.GC_FGD,cv2.GC_PR_FGD]).astype(np.uint8)*255
    a[706:,:] = 0
    Image.fromarray(np.dstack([rgb,a])).crop((320,0,960,720)).save(ASSETS/(key+".png"))

shutil.copyfile("D:/files/Pictures/保存素材/岁己_小鸟跳静态图.png", ASSETS/"bird.png")
sheet = Image.new("RGBA", (1440,720), (230,225,242,255))
for i,key in enumerate(["cookie","sui-back","sui-front","bird"]):
    im=Image.open(ASSETS/(key+".png")).convert("RGBA")
    im.thumbnail((340,660))
    sheet.alpha_composite(im,(i*360+(360-im.width)//2,40))
ImageDraw.Draw(sheet).text((15,12),"cookie | SUI back | SUI front | little bird",fill="black")
sheet.convert("RGB").save(OUT/"sticker-intro/stickers.jpg")
print(ASSETS)
