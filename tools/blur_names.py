#!/usr/bin/env python3
"""Blur personal names in screenshots before publishing.

OCRs each image (tesseract, upscaled for small UI text), finds words matching the
patterns, and blurs a padded box around each hit in place. Prints hits per file and
exits non-zero if a second pass still finds a match.

usage: blur_names.py PATTERN_REGEX IMAGE...
"""
import re, subprocess, sys
from PIL import Image, ImageFilter

UPSCALE = 2


def find(path, rx):
    img = Image.open(path).convert("RGB")
    big = img.resize((img.width * UPSCALE, img.height * UPSCALE), Image.LANCZOS)
    tmp = "/tmp/claude-1000/blur_ocr.png"
    big.save(tmp)
    tsv = subprocess.run(["tesseract", tmp, "-", "--psm", "11", "tsv"], capture_output=True, text=True).stdout
    boxes = []
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) == 12 and f[11].strip() and rx.search(f[11]):
            x, y, w, h = (int(v) // UPSCALE for v in f[6:10])
            boxes.append((x, y, w, h, f[11]))
    return img, boxes


def main():
    rx = re.compile(sys.argv[1], re.I)
    leftover = 0
    for path in sys.argv[2:]:
        img, boxes = find(path, rx)
        for x, y, w, h, word in boxes:
            pad_x, pad_y = max(6, w // 3), max(4, h // 2)
            box = (max(0, x - pad_x), max(0, y - pad_y), min(img.width, x + w + pad_x), min(img.height, y + h + pad_y))
            region = img.crop(box).filter(ImageFilter.GaussianBlur(max(6, h // 2)))
            img.paste(region, box)
        if boxes:
            img.save(path)
        again = find(path, rx)[1]
        leftover += len(again)
        print(f"{path}: blurred {[b[4] for b in boxes]}; remaining {[b[4] for b in again]}")
    sys.exit(1 if leftover else 0)


if __name__ == "__main__":
    main()
