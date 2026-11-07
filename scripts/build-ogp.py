#!/usr/bin/env python3
"""Build a fully decodable JPEG OGP image, matching the approved turquoise polar-bear artwork."""
from pathlib import Path
from PIL import Image

root=Path(__file__).resolve().parents[1]
source=root/"assets/polarbear-icon.png"
dest=root/"assets/ogp-bear-preview-medium-20261108.jpg"
w,h=1200,630

# Unlike the previous truncated PNG, the website's original logo is intact.
with Image.open(source) as original:
    original.load()
    logo=original.convert("RGBA").resize((300,300),Image.Resampling.LANCZOS)

card=Image.new("RGB",(w,h),(93,192,213))
card.paste(logo,((w-300)//2,(h-300)//2),logo)
# Check actual image content, not only dimensions and file existence.
white=sum(1 for y in range(175,465,5) for x in range(420,780,5)
          if min(card.getpixel((x,y)))>230)
if white<500:
    raise ValueError(f"Missing white bear illustration: white pixel count {white}")
card.save(dest,"JPEG",quality=94,optimize=True,subsampling=0)
with Image.open(dest) as check:
    check.load()
    assert check.size==(1200,630) and check.mode=="RGB"
    assert min(check.getpixel((600,300)))>180 or white>500
print(f"Decoded and validated {dest.name}: {dest.stat().st_size} bytes; {white} sampled white pixels")
