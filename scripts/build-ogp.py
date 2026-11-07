#!/usr/bin/env python3
"""Use the exact cropped community logo supplied by the owner in the social preview."""
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"assets/ogp-logo-crop.png"
TARGET=ROOT/"assets/ogp-card.jpg"
W,H=1200,630
logo=Image.open(SOURCE).convert("RGB")
target_width=740
target_height=round(logo.height*target_width/logo.width)
logo=logo.resize((target_width,target_height),Image.Resampling.LANCZOS)
card=Image.new("RGB",(W,H),"white")
card.paste(logo,((W-target_width)//2,(H-target_height)//2))
TARGET.parent.mkdir(parents=True,exist_ok=True)
card.save(TARGET,"JPEG",quality=92,optimize=True,subsampling=0)
assert Image.open(TARGET).size==(W,H)
print(f"Created {TARGET} from cropped owner-supplied logo ({TARGET.stat().st_size} bytes)")
