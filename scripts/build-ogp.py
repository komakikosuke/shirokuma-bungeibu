#!/usr/bin/env python3
"""Generate a horizontal OGP preview without cropping the original book."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"assets/book-shell-from-top.jpg"
TARGET=ROOT/"assets/ogp-card.jpg"
W,H=1200,630

bg=Image.new("RGB",(W,H))
p=bg.load()
for y in range(H):
    for x in range(W):
        v=max(0,1-((x-520)/950)**2-((y-250)/850)**2)
        p[x,y]=(int(153+18*v),int(216+15*v),int(230+11*v))

book=Image.open(SOURCE).convert("RGB")
book=ImageOps.contain(book,(345,475),Image.Resampling.LANCZOS)
bw,bh=book.size
bx=273+(345-bw)//2
by=(H-bh)//2
shadow=Image.new("RGBA",(W,H),(0,0,0,0))
sd=ImageDraw.Draw(shadow)
sd.rounded_rectangle((bx+7,by+12,bx+bw+9,by+bh+14),radius=8,fill=(24,68,92,110))
shadow=shadow.filter(ImageFilter.GaussianBlur(19))
bg=Image.alpha_composite(bg.convert("RGBA"),shadow)
bg.paste(book,(bx,by))

d=ImageDraw.Draw(bg)
font_path=next((str(p) for p in [
 Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
 Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
 Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc")
] if p.exists()),None)
if not font_path:
    raise RuntimeError("Japanese Noto CJK font not installed")
font_large=ImageFont.truetype(font_path,51)
font_small=ImageFont.truetype(font_path,25)
font_english=ImageFont.truetype(font_path,17)
navy=(23,65,90,255)
muted=(53,99,120,255)
x=650
d.text((x,213),"シロクマ文芸部",font=font_large,fill=navy)
d.line((x,302,1020,302),fill=(90,161,183,255),width=2)
d.text((x,325),"クリエイターの帰る場所。",font=font_small,fill=muted)
d.text((x,380),"SHIROKUMA BUNGEIBU",font=font_english,fill=muted)

TARGET.parent.mkdir(parents=True,exist_ok=True)
bg.convert("RGB").save(TARGET,"JPEG",quality=90,optimize=True,subsampling=0)
assert Image.open(TARGET).size==(1200,630)
print("Created",TARGET,"bytes",TARGET.stat().st_size)
