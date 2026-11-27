#!/usr/bin/env python3
"""Install the browser-downloaded, verified long BGM into the public site assets."""
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

TARGET = Path("twenty-credits/assets/arishihi-no-teiryusho-long.mp3")
SOURCE = "https://shirokuma-writing-room.komakikosuke.chatgpt.site/endroll-audio/arishihi-no-teiryusho-long.mp3"
EXPECTED_SHA256 = "b686c1043711fee238127a4a63cbccb90f4b3902fef0a23c3142ea292a1afa9b"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    if TARGET.exists():
        if digest(TARGET) != EXPECTED_SHA256:
            raise ValueError("Existing audio differs from the verified source")
        print("Verified long soundtrack already installed")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        request = Request(SOURCE, headers={"User-Agent": "ShirokumaEndrollSync/1.0 (+https://github.com/komakikosuke/shirokuma-bungeibu)"})
        with urlopen(request, timeout=45) as response, tempfile.NamedTemporaryFile(dir=TARGET.parent, suffix=".mp3", delete=False) as output:
            temporary = Path(output.name)
            count = 0
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > 25 * 1024 * 1024:
                    raise ValueError("Unexpected audio size")
                output.write(chunk)
        if digest(temporary) != EXPECTED_SHA256:
            raise ValueError("Downloaded audio failed SHA-256 verification")
        os.replace(temporary, TARGET)
        print(f"Installed verified LONG 10:46 soundtrack ({count} bytes)")
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    main()
