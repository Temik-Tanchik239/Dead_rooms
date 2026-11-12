"""Рисует стартовые картинки инвентаря (их можно заменить своими, пути лежат в assets/inventory.json):
  assets/ui/inventory_panel.png, inventory_slot.png, inventory_slot_hand.png — окно и ячейки;
  assets/ui/inventory_skeleton.png — «скелет» для слотов экипировки (equipment.model.image, 200×300);
  assets/icons/stub_*.png — иконки предметов-заглушек (шлем, амулет, перчатка, пояс, ботинок, три артефакта).
Запуск: python make_inventory_textures.py (нужен pygame). Размер своих картинок любой — игра сама растянет под размеры из конфига."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from pathlib import Path
import pygame as pg

ROOT = Path(__file__).resolve().parent / "assets"
K = 4   # рисуем в 4 раза крупнее и уменьшаем — линии получаются гладкими

def panel(w=920, h=496):
    s = pg.Surface((w, h), pg.SRCALPHA)
    for y in range(h):   # мягкий вертикальный градиент
        k = y / h; pg.draw.line(s, (int(26 - 8 * k), int(28 - 8 * k), int(44 - 14 * k), 242), (0, y), (w, y))
    mask = pg.Surface((w, h), pg.SRCALPHA); pg.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=12)
    s.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MIN)
    pg.draw.rect(s, (120, 110, 160), s.get_rect(), 2, border_radius=12)
    pg.draw.rect(s, (60, 54, 90), s.get_rect().inflate(-8, -8), 1, border_radius=9)
    return s

def slot(n, accent):
    s = pg.Surface((n, n), pg.SRCALPHA)
    pg.draw.rect(s, (34, 38, 56, 255), s.get_rect(), border_radius=7)
    pg.draw.rect(s, (22, 24, 38, 255), s.get_rect().inflate(-8, -8), border_radius=5)
    pg.draw.rect(s, accent, s.get_rect(), 2, border_radius=7)
    return s

def skeleton(w=200, h=300):
    """Скелет спереди. Точки тела совпадают со слотами по умолчанию: голова (100,30), шея (100,68), кисти (30,206) и (170,206),
    таз/пояс (100,166), стопы (78,282) и (122,282)."""
    bone, edge, dark = (226, 220, 200), (120, 112, 96), (24, 22, 30)
    s = pg.Surface((w * K, h * K), pg.SRCALPHA)
    P = lambda x, y: (int(x * K), int(y * K))
    def line(a, b, t):   # кость: светлая линия с тёмной окантовкой и круглыми концами
        for col, width in ((edge, t + 2), (bone, t)):
            pg.draw.line(s, col, P(*a), P(*b), int(width * K))
            for p in (a, b): pg.draw.circle(s, col, P(*p), int(width * K / 2))
    def ellipse(rect, fill=bone, width=0):
        x, y, ww, hh = rect; r = pg.Rect(int(x * K), int(y * K), int(ww * K), int(hh * K))
        pg.draw.ellipse(s, fill, r, int(width * K) if width else 0)
    # позвоночник и шея
    for y in range(58, 178, 6): ellipse((95, y, 10, 5.2)); ellipse((95, y, 10, 5.2), edge, 0.8)
    # рёбра и грудина
    for k in range(7):
        y = 92 + k * 8.5; half = 22 + (k if k < 4 else 6 - k) * 4.2
        for sgn in (-1, 1):
            pts = [P(100 + sgn * 5, y), P(100 + sgn * half * 0.7, y - 4), P(100 + sgn * half, y + 4), P(100 + sgn * half * 0.8, y + 12)]
            pg.draw.lines(s, edge, False, pts, int(5.6 * K)); pg.draw.lines(s, bone, False, pts, int(3.4 * K))
    line((100, 92), (100, 146), 6)
    # ключицы, плечи
    line((100, 86), (64, 92), 4); line((100, 86), (136, 92), 4)
    # руки: плечо, локоть, запястье, кисть (веер костей)
    for sgn in (-1, 1):
        sh, el, wr = (100 + sgn * 38, 92), (100 + sgn * 56, 150), (100 + sgn * 68, 200)
        line(sh, el, 6); line(el, wr, 5)
        for dx in (-5, -1.5, 2, 5.5): line((wr[0], wr[1]), (wr[0] + sgn * dx * 0.9 - sgn * 1, wr[1] + 14 + abs(dx) * 0.4), 2.2)
    # таз
    for sgn in (-1, 1):
        pts = [P(100, 152), P(100 + sgn * 34, 158), P(100 + sgn * 42, 180), P(100 + sgn * 20, 196), P(100, 184)]
        pg.draw.polygon(s, bone, pts); pg.draw.polygon(s, edge, pts, int(1.6 * K))
    ellipse((92, 176, 16, 14), dark)
    # ноги: бедро, колено, голень, стопа
    for sgn in (-1, 1):
        hip, kn, an = (100 + sgn * 18, 190), (100 + sgn * 22, 244), (100 + sgn * 20, 276)
        line(hip, kn, 8); line(kn, an, 6); ellipse((100 + sgn * 22 - 6, 240, 12, 10), bone); ellipse((100 + sgn * 22 - 6, 240, 12, 10), edge, 1)
        line((an[0] - 8, 284), (an[0] + 8, 284), 6); line((an[0] - sgn * 2, 284), (an[0] - sgn * 2, 291), 4)
    # череп: черепная коробка, глазницы, нос, челюсть и зубы
    ellipse((78, 8, 44, 40), edge); ellipse((79.5, 9.5, 41, 37))
    ellipse((86, 40, 28, 15), edge); ellipse((87.5, 41.5, 25, 12))
    for cx in (90.5, 109.5): ellipse((cx - 6, 24, 12, 13), dark)
    pg.draw.polygon(s, dark, [P(100, 36), P(96.5, 43), P(103.5, 43)])
    for x in range(89, 112, 4): pg.draw.line(s, edge, P(x, 48), P(x, 53), int(1.2 * K))
    return pg.transform.smoothscale(s, (w, h))

def _icon():
    return pg.Surface((48 * K, 48 * K), pg.SRCALPHA)

def icon_helmet():
    s = _icon(); P = lambda x, y: (int(x * K), int(y * K))
    pg.draw.ellipse(s, (120, 130, 150), (P(9, 8)[0], P(9, 8)[1], 30 * K, 32 * K)); pg.draw.rect(s, (120, 130, 150), (*P(9, 26), 30 * K, 14 * K))
    pg.draw.rect(s, (60, 66, 84), (*P(13, 24), 22 * K, 6 * K)); pg.draw.line(s, (200, 210, 230), P(24, 8), P(24, 24), 2 * K)
    pg.draw.ellipse(s, (170, 180, 200), (*P(14, 11), 8 * K, 6 * K)); return s

def icon_amulet():
    s = _icon(); P = lambda x, y: (int(x * K), int(y * K))
    pg.draw.lines(s, (200, 170, 80), False, [P(10, 6), P(16, 22), P(24, 28), P(32, 22), P(38, 6)], 2 * K)
    pg.draw.polygon(s, (90, 200, 220), [P(24, 26), P(32, 34), P(24, 44), P(16, 34)]); pg.draw.polygon(s, (200, 170, 80), [P(24, 26), P(32, 34), P(24, 44), P(16, 34)], 2 * K)
    pg.draw.polygon(s, (190, 240, 250), [P(24, 29), P(27, 34), P(24, 37), P(21, 34)]); return s

def icon_glove():
    s = _icon(); P = lambda x, y: (int(x * K), int(y * K)); col = (150, 100, 60)
    pg.draw.rect(s, col, (*P(14, 26), 20 * K, 16 * K), border_radius=3 * K)
    for i, x in enumerate((13, 19, 25, 31)): pg.draw.rect(s, col, (*P(x, 8 + abs(i - 1.5) * 2), 5 * K, 22 * K), border_radius=2 * K)
    pg.draw.ellipse(s, col, (*P(7, 24), 10 * K, 6 * K)); pg.draw.rect(s, (90, 60, 40), (*P(13, 38), 22 * K, 5 * K)); return s

def icon_belt():
    s = _icon(); P = lambda x, y: (int(x * K), int(y * K))
    pg.draw.rect(s, (110, 70, 40), (*P(4, 18), 40 * K, 12 * K), border_radius=2 * K)
    pg.draw.rect(s, (210, 175, 80), (*P(17, 14), 14 * K, 20 * K), border_radius=2 * K); pg.draw.rect(s, (110, 70, 40), (*P(21, 19), 6 * K, 10 * K))
    for x in (8, 12, 36, 40): pg.draw.circle(s, (210, 175, 80), P(x, 24), K); return s

def icon_boot():
    s = _icon(); P = lambda x, y: (int(x * K), int(y * K)); col = (120, 84, 56)
    pg.draw.polygon(s, col, [P(14, 6), P(28, 6), P(28, 28), P(42, 34), P(42, 42), P(10, 42), P(10, 30), P(14, 30)])
    pg.draw.rect(s, (80, 56, 38), (*P(10, 38), 32 * K, 5 * K)); pg.draw.rect(s, (190, 150, 90), (*P(14, 8), 14 * K, 4 * K)); return s

def icon_gem(main, light):
    s = _icon(); P = lambda x, y: (int(x * K), int(y * K))
    pts = [P(24, 4), P(40, 16), P(36, 38), P(24, 45), P(12, 38), P(8, 16)]
    pg.draw.polygon(s, main, pts); pg.draw.polygon(s, light, [P(24, 4), P(40, 16), P(24, 22), P(8, 16)])
    pg.draw.polygon(s, tuple(int(v * 0.6) for v in main), [P(24, 22), P(36, 38), P(24, 45), P(12, 38)]); pg.draw.polygon(s, (255, 255, 255), pts, K)
    pg.draw.circle(s, (255, 255, 255), P(18, 14), 2 * K); return s

if __name__ == "__main__":
    pg.init(); pg.display.set_mode((1, 1)); (ROOT / "ui").mkdir(parents=True, exist_ok=True); (ROOT / "icons").mkdir(parents=True, exist_ok=True)
    out = {"ui/inventory_panel.png": panel(), "ui/inventory_slot.png": slot(64, (88, 84, 120)), "ui/inventory_slot_hand.png": slot(96, (150, 120, 70)),
           "ui/inventory_skeleton.png": skeleton()}
    icons = {"stub_helmet": icon_helmet(), "stub_amulet": icon_amulet(), "stub_glove": icon_glove(), "stub_belt": icon_belt(), "stub_boot": icon_boot(),
             "stub_artifact_red": icon_gem((200, 50, 60), (250, 130, 130)), "stub_artifact_blue": icon_gem((60, 110, 230), (140, 180, 255)),
             "stub_artifact_green": icon_gem((50, 180, 90), (140, 230, 160))}
    for name, surf in icons.items(): out[f"icons/{name}.png"] = pg.transform.smoothscale(surf, (48, 48))
    for name, surf in out.items(): pg.image.save(surf, str(ROOT / name)); print("saved", ROOT / name)
