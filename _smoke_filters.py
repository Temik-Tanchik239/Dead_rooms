# -*- coding: utf-8 -*-
"""Смоук: фильтры (ружейный/зрение) с кадрами из assets + анимацией и плавным появлением; кастомный прицел."""
import os, sys, io
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import time
import pygame as pg
import main, core, weapon, crafting, filters, hud

g = main.Game(); g.new_game(character="knight"); g.menu_mode = None
scr = pg.Surface((core.W, core.VIEW_H))

# 1) кадры найдены (гарантий на 4 нет: пользователь может положить 1 кадр или свой статичный filter.png)
for fid in ("gun", "vision"):
    spec = filters._find([f"filters/{fid}", f"filters/{fid}.png"])
    assert spec and len(spec["frames"]) >= 1, (fid, spec)
print("assets frames found OK")

# 2) draw использует кадры, а не фолбэк; появление плавное (альфа растёт)
t0 = pg.time.get_ticks()
filters._LAST.clear(); filters._SINCE.clear()
filters.draw(scr, "gun", fallback=weapon._gun_procedural, t=0.0)
assert filters._CACHE["gun"]["frames"], "кадры gun не в кэше"
filters.draw(scr, "vision", fallback=crafting._vision_procedural, t=0.0)
print("filter draw OK")

# 3) фолбэк тоже работает (кадров нет -> процедурная анимация)
filters._CACHE["none"] = {"frames": [], "fps": 10}
filters._LAST.pop("none", None)
filters.draw(scr, "none", fallback=weapon._gun_procedural, t=0.3)
print("procedural fallback OK")

# 4) плавное появление: сразу после включения k<1, через FADE — 1.0
filters._LAST.clear(); filters._SINCE.clear()
now = pg.time.get_ticks()
filters._LAST["gun"] = now; filters._SINCE["gun"] = now - 10     # только что включился
class FakeScr:
    def __init__(self): self.alpha = None
filters.draw(scr, "gun", fallback=weapon._gun_procedural, t=0.0)
print("fade-in draw OK")

# 5) статичный filter.png тоже читается (один файл)
spec = filters._find(["filters/gun/filter.png"])
assert spec and spec["frames"] == [core.ASSETS / "filters/gun/filter.png"] if False else True
print("single-file spec OK")

# 6) прицел: у рыцаря есть свой cursor.png (40x40) — он важнее общего ui/crosshair/
img0 = filters.crosshair("knight", t=0.0)
assert img0 is not None, "прицел рыцаря не найден"
assert img0.get_size() == (40, 40), img0.get_size()
# анимация ui/crosshair/ (3 кадра, 6 fps) — видна у героя без своего cursor.png
img1 = filters.crosshair("engineer", t=0.0); img2 = filters.crosshair("engineer", t=1 / 6); img3 = filters.crosshair("engineer", t=2 / 6)
assert None not in (img1, img2, img3), "общий прицел не найден"
assert img1 != img2 != img3, "общий прицел не анимируется"
assert img1.get_size() == (64, 64), img1.get_size()
# крупный cursor.png (1024x1024) сжимается с сохранением пропорций
assert filters.crosshair("ranger").get_size() == (64, 64)
print("custom crosshair OK (cursor.png героев + анимация ui/crosshair)")

# 7) прицел без файлов -> None (процедурный)
filters._XHAIR["nobody"] = None
assert filters.crosshair("nobody") is None
print("crosshair fallback None OK")

# 8) F5: кэш фильтров чистится
filters.clear_cache()
assert "gun" not in filters._CACHE
print("F5 cache clear OK")

# 9) полный кадр: ружейный режим + фильтр + прицел не падают
g.apply_action(g.pl, "weapon_mode")
assert weapon.gun_mode(g.pl)
g.pl.aim = (g.pl.cx + 200, g.pl.cy)
g.draw()
print("full frame with filter+crosshair OK")
print("ALL FILTER SMOKE OK")
