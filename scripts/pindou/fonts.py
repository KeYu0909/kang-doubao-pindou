"""Bundled OFL Chinese UI font; no host font lookup or runtime download."""
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont
FONT_PATH=Path(__file__).resolve().parents[2]/'assets/fonts/KangPindouUI-Regular.ttf'

@lru_cache(maxsize=8)
def png_font(size):
    return ImageFont.truetype(str(FONT_PATH),size=size)

@lru_cache(maxsize=1)
def register_pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('KangPindouUI',str(FONT_PATH)))
    return 'KangPindouUI'
