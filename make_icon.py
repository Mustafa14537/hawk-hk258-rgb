"""HK258 RGB uygulama logosunu uretir: app.ico (16-256 px) ve app.png (tepsi simgesi icin).
Koyu yuvarlak kare zemin + RGB gecisli Hawk kanadi (panel basligindaki isaretle ayni cizgi)."""
import colorsys
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
# panel basligindaki isaret: M3 15 l5-6 4 4 4-7 5 9 (24 birimlik kutuda)
WING = [(3, 15), (8, 9), (12, 13), (16, 6), (21, 15)]


def render(size, stroke_ratio):
    ss = 4                                   # yumusak kenarlar icin 4x buyuk ciz, sonra kucult
    S = size * ss
    radius = int(S * 0.24)

    # zemin: koyu dikey gecis
    bg = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(bg)
    for y in range(S):
        t = y / S
        c = tuple(int(a + (b - a) * t) for a, b in zip((30, 35, 48), (10, 12, 17)))
        d.line([(0, y), (S, y)], fill=c + (255,))

    # RGB yatay gecis (kirmizi -> mor)
    grad = Image.new("RGBA", (S, S))
    g = ImageDraw.Draw(grad)
    for x in range(S):
        r, gg, b = colorsys.hsv_to_rgb(0.0 + 0.82 * x / S, 0.95, 1.0)
        g.line([(x, 0), (x, S)], fill=(int(r * 255), int(gg * 255), int(b * 255), 255))

    # kanat maskesi (kutunun ortasina olcekli)
    pad = S * 0.16
    scale = (S - 2 * pad) / 18.0            # cizginin x araligi 3..21 = 18 birim
    yoff = (S - 9 * scale) / 2 - 6 * scale   # y araligi 6..15 = 9 birim, dikeyde ortala
    pts = [(pad + (x - 3) * scale, yoff + y * scale) for x, y in WING]
    w = max(2, int(S * stroke_ratio))
    mask = Image.new("L", (S, S), 0)
    m = ImageDraw.Draw(mask)
    m.line(pts, fill=255, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):          # yuvarlak uclar
        m.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)

    # parilti
    glow = mask.filter(ImageFilter.GaussianBlur(S * 0.05)).point(lambda v: int(v * 0.85))
    img = bg.copy()
    img.paste(grad, (0, 0), glow)
    img.paste(grad, (0, 0), mask)

    # ince kenar cizgisi + yuvarlak kose kesimi
    edge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle([1, 1, S - 2, S - 2], radius=radius,
                                           outline=(255, 255, 255, 38), width=max(1, S // 128))
    img = Image.alpha_composite(img, edge)
    shape = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shape).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)
    img.putalpha(shape)
    return img.resize((size, size), Image.LANCZOS)


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    # kucuk boyutlarda cizgiyi kalinlastir ki okunabilsin
    frames = {s: render(s, 0.13 if s <= 24 else 0.11 if s <= 48 else 0.085) for s in sizes}
    frames[256].save(os.path.join(HERE, "app.ico"), sizes=[(s, s) for s in sizes],
                     append_images=[frames[s] for s in sizes[:-1]])
    frames[256].save(os.path.join(HERE, "app.png"))
    # onizleme seridi
    strip = Image.new("RGBA", (sum(sizes) + 10 * len(sizes), 256), (40, 40, 40, 255))
    x = 0
    for s in sizes:
        strip.paste(frames[s], (x, 256 - s), frames[s])
        x += s + 10
    strip.save(os.path.join(HERE, "icon_preview.png"))
    print("app.ico, app.png, icon_preview.png yazildi")


if __name__ == "__main__":
    main()
