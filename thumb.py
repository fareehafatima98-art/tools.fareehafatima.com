"""
Personalised email thumbnail generator (Outbound Readiness Score cards).

For each prospect, builds a card that looks like a paused video of their own
website: mShots screenshot backdrop, dark gradient, OUTBOUND READINESS SCORE pill,
centred play button, and "Prepared for <name> / <company> ..." caption.
Variant A is clean; variant B adds Fareeha's face bubble (assets/face.jpg).

Stored in Vercel Blob as thumbs/<slug>.jpg and thumbs/<slug>-face.jpg and
served through /thumbs/<file> on our own domain so the email's <img src>
never points at blob storage directly.

mShots (s0.wp.com) returns a small "Generating Preview" placeholder until the
real screenshot is rendered; we poll until the image is full-width.
"""
import io, os, time, pathlib, urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = pathlib.Path(__file__).resolve().parent
ASSETS = HERE / "assets"

W, H = 1200, 750          # 2x of the 600x375 email display size
JPEG_QUALITY = 82

CAPTION_SUB = "1 min 11 sec  ·  two changes I’d test first"
PILL_TEXT = "OUTBOUND READINESS SCORE"

def _font(name, size):
    return ImageFont.truetype(str(ASSETS / name), size)

def fetch_shot(domain: str, tries: int = 12, wait: float = 2.5) -> Image.Image:
    """Fetch the mShots screenshot, polling past the 'Generating Preview'
    placeholder (which comes back well under 600px wide)."""
    url = f"https://s0.wp.com/mshots/v1/https%3A%2F%2F{domain}?w=1280&h=800"
    last = None
    for i in range(tries):
        req = urllib.request.Request(url + f"&r={i}",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        last = img
        if img.width >= 600:
            return img
        time.sleep(wait)
    return last  # best effort: caller may accept the placeholder or fail

def _cover(img: Image.Image) -> Image.Image:
    """Scale-and-crop to WxH, keeping the top of the page visible."""
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)))
    left = (img.width - W) // 2
    return img.crop((left, 0, left + W, H))

def _gradient() -> Image.Image:
    """Vertical dark gradient overlay, light at top, heavy at bottom."""
    g = Image.new("L", (1, H))
    for y in range(H):
        t = y / H
        if t < 0.55:
            a = 30 + (t / 0.55) * 34          # 30 -> 64
        else:
            a = 64 + ((t - 0.55) / 0.45) * 145  # 64 -> 209
        g.putpixel((0, y), int(a))
    overlay = Image.new("RGB", (W, H), (10, 10, 14))
    mask = g.resize((W, H))
    return overlay, mask

def _rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)

def compose(shot: Image.Image, first_name: str, last_name: str,
            company: str, with_face: bool) -> bytes:
    im = _cover(shot)
    overlay, mask = _gradient()
    im.paste(overlay, (0, 0), mask)
    d = ImageDraw.Draw(im)

    # pill top-left
    pf = _font("DejaVuSans-Bold.ttf", 22)
    pt = PILL_TEXT
    # letter-spaced text: draw char by char
    spacing = 4
    tw = sum(d.textlength(c, font=pf) + spacing for c in pt) - spacing
    px, py, pad_x, pad_y = 32, 32, 24, 13
    _rounded(d, (px, py, px + tw + pad_x * 2, py + 22 + pad_y * 2),
             radius=26, fill=(255, 255, 255, 240))
    x = px + pad_x
    for c in pt:
        d.text((x, py + pad_y - 2), c, font=pf, fill=(17, 17, 17))
        x += d.textlength(c, font=pf) + spacing

    # play button centre (slightly above middle)
    cx, cy, r = W // 2, int(H * 0.44), 86
    # soft shadow
    sh = Image.new("RGBA", (r * 4, r * 4), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((r, r, r * 3, r * 3), fill=(0, 0, 0, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    im.paste(sh, (cx - r * 2, cy - r * 2 + 10), sh)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255))
    tri = [(cx - 24, cy - 34), (cx - 24, cy + 34), (cx + 38, cy)]
    d.polygon(tri, fill=(17, 17, 17))

    # face bubble (variant B)
    text_left = 40
    if with_face:
        face = Image.open(ASSETS / "face.jpg").convert("RGB").resize((190, 190))
        m = Image.new("L", (190, 190), 0)
        ImageDraw.Draw(m).ellipse((0, 0, 190, 190), fill=255)
        fx, fy = 36, H - 190 - 150
        # white ring
        d.ellipse((fx - 6, fy - 6, fx + 196, fy + 196), fill=(255, 255, 255))
        im.paste(face, (fx, fy), m)

    # caption
    who = f"{first_name} {last_name}".strip() or company
    name = f"Prepared for {who}"
    nf = _font("DejaVuSerif-Bold.ttf", 44)
    sf = _font("DejaVuSans.ttf", 26)
    d.text((text_left, H - 118), name, font=nf, fill=(255, 255, 255))
    sub = CAPTION_SUB if who == company else f"{company}  ·  {CAPTION_SUB}"
    d.text((text_left, H - 58), sub,
           font=sf, fill=(255, 255, 255, 235))

    out = io.BytesIO()
    im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()

class ThumbError(Exception):
    pass

def generate(domain: str, first_name: str, last_name: str, company: str,
             variants=("plain", "face")) -> dict:
    """Fetch the screenshot once, compose requested variants, return
    {variant: jpeg_bytes}. Raises ThumbError if mShots never gets past the
    placeholder."""
    shot = fetch_shot(domain)
    if shot is None or shot.width < 600:
        raise ThumbError(f"mShots still returning placeholder for {domain}")
    out = {}
    if "plain" in variants:
        out["plain"] = compose(shot, first_name, last_name, company, False)
    if "face" in variants:
        out["face"] = compose(shot, first_name, last_name, company, True)
    return out
