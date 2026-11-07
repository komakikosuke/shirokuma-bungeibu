#!/usr/bin/env python3
"""Create a robust RGB/JPEG social preview from the owner's polar bear artwork."""
from pathlib import Path
from PIL import Image

root=Path(__file__).resolve().parents[1]
source=root/"assets/ogp-user-bear.png"
dest=root/"assets/ogp-bear-preview-20261108.jpg"

with Image.open(source) as image:
    image.load()  # Force full decoding, not just header parsing.
    if image.size != (1200,630):
        raise ValueError(f"Unexpected original OGP image size: {image.size}")
    image=image.convert("RGB")
    # The center must show the pale/white polar bear, not the blue background.
    white=sum(1 for y in range(190,460,5) for x in range(400,800,5)
              if min(image.getpixel((x,y))) > 230)
    cyan=sum(1 for y in range(0,140,10) for x in range(0,1200,20)
             if image.getpixel((x,y))[2] > image.getpixel((x,y))[0]+35)
    if white<500 or cyan<300:
        raise ValueError(f"OGP image content mismatch (bear pixels={white}, background pixels={cyan})")
    image.save(dest,"JPEG",quality=93,optimize=True,subsampling=0)

with Image.open(dest) as verify:
    verify.load()
    if verify.size != (1200,630) or verify.mode != "RGB":
        raise ValueError("New JPG preview failed validation")
print(f"Validated {dest.name}: {dest.stat().st_size} bytes, bear pixels={white}, cyan pixels={cyan}")
