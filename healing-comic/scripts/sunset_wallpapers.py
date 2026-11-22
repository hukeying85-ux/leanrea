#!/usr/bin/env python3
"""Create mock lock-screen overlays and an ordered wallpaper contact sheet.

The clock and date are illustrative, not a live device screenshot. Run again
once all ten art files are approved. Requires Pillow and DejaVu fonts.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path('healing-comic/deliverables/xhs-sunset/recreated')
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def run():
    files = sorted((ROOT / 'art').glob('*.png'))
    assert len(files) <= 10 and files, 'Expected at most ten source images'
    ui = ROOT / 'ui'
    ui.mkdir(parents=True, exist_ok=True)
    previews = []
    for file in files:
        im = Image.open(file).convert('RGBA')
        w, h = im.size
        draw = ImageDraw.Draw(im)
        def text_center(y, text, size, face=FONT):
            f = ImageFont.truetype(face, size)
            draw.text((w / 2 + 1, y + 2), text, font=f, fill=(53, 41, 38, 100), anchor='mt')
            draw.text((w / 2, y), text, font=f, fill=(255, 255, 255, 240), anchor='mt')
        text_center(int(h * .057), 'SUNDAY, JUNE 22', int(w * .033), BOLD)
        text_center(int(h * .089), '18:26', int(w * .148))
        # Decorative lock screen home indicator; values and time are examples.
        draw.rounded_rectangle((w*.38, h*.962, w*.62, h*.969), radius=5, fill=(255,255,255,215))
        im.convert('RGB').save(ui / file.name, optimize=True)
        thumb = ImageOps.contain(Image.open(file).convert('RGB'), (240, 430))
        previews.append((file.stem[:2], thumb))
    sheet = Image.new('RGB', (1308, 930), '#fff4eb')
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT, 18)
    # Position by file number so a missing image stays visibly empty.
    for number, im in previews:
        idx = int(number)-1
        x, y = 18 + idx % 5 * 258, 18 + idx // 5 * 452
        sheet.paste(im, (x,y))
        d.rounded_rectangle((x+8,y+8,x+42,y+37), radius=7, fill='#fff4e5')
        d.text((x+14,y+11), number, font=font, fill='#8a563f')
    sheet.save(ROOT / ('10张总预览.jpg' if len(files) == 10 else '未完成-预览.jpg'), quality=90)

if __name__ == '__main__':
    run()
