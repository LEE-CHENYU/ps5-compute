"""Bake the bundled OFL-licensed Barlow font into framebuffer alpha glyphs."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
font_path=str(ROOT/'assets/fonts/Barlow-Regular.ttf')
(ROOT/'build').mkdir(exist_ok=True)
out=['typedef struct { unsigned offset; unsigned short width,height,advance; } ml_glyph;',
     'typedef struct { const unsigned char *pixels; const ml_glyph *glyphs; unsigned height; } ml_font;']
for size in [22,28,40,60]:
    font=ImageFont.truetype(font_path,size,index=0)
    data=[];glyphs=[]
    for code in range(32,127):
        char=chr(code);advance=round(font.getlength(char));w=max(advance+4,1);h=size+10
        bitmap=Image.new('L',(w,h));ImageDraw.Draw(bitmap).text((0,0),char,font=font,fill=255,anchor='la')
        glyphs.append((len(data),w,h,advance));data.extend(bitmap.tobytes())
    out.append(f'static const unsigned char font_pixels_{size}[]={{'+','.join(map(str,data))+'};')
    out.append(f'static const ml_glyph font_glyphs_{size}[]={{'+','.join('{'+','.join(map(str,g))+'}' for g in glyphs)+'};')
    out.append(f'static const ml_font font_{size}={{font_pixels_{size},font_glyphs_{size},{size+10}}};')
(ROOT/'build/fonts.h').write_text('\n'.join(out)+'\n')
print('Baked Barlow glyphs for 1080p dashboard')
