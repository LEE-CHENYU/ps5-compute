"""Render the project's own icon using the bundled open font."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def make_icon():
    image = Image.new('RGB', (1024, 1024), '#142235')
    draw = ImageDraw.Draw(image)
    font = str(ROOT / 'assets/fonts/Barlow-Regular.ttf')
    draw.rectangle((86, 86, 102, 222), fill='#63b8e8')
    draw.text((134, 94), 'PS5', font=ImageFont.truetype(font, 110), fill='#f0f4f8')
    draw.text((86, 236), 'Compute', font=ImageFont.truetype(font, 100), fill='#f0f4f8')
    for row in range(3):
        for col in range(5):
            x, y = 90 + col * 170, 453 + row * 139
            draw.rounded_rectangle((x, y, x + 131, y + 99), radius=13,
                                   fill='#7ce0bf' if col <= row + 1 else '#30475f')
    draw.text((90, 903), 'Native GPU lab', font=ImageFont.truetype(font, 39), fill='#9cb4ca')
    return image


if __name__ == '__main__':
    (ROOT / 'build').mkdir(exist_ok=True)
    make_icon().resize((512, 512), Image.Resampling.LANCZOS).save(ROOT / 'build/icon0.png')
