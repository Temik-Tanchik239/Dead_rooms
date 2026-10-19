"""Общее для всех модулей: пути, конфиги из data/*.json, размеры поля, физическое тело, мелкие функции."""
import json, sys
from pathlib import Path
import pygame as pg

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
DATA = BASE / "data"      # в .exe-версии data и assets лежат рядом с exe, их можно править
ASSETS = BASE / "assets"
T, COLS, ROWS = 32, 50, 50      # размер карты в клетках: 50 x 50
MW, MH = COLS * T, ROWS * T      # размер карты в пикселях
VIEW_H = 16 * T                  # высота игрового окна (камера показывает кусок карты)
PANEL_H = 56                     # высота нижней панели (HUD)
W, H = 30 * T, VIEW_H + PANEL_H  # размер окна: игровое поле + панель HUD
CFG = {}
DATA_FILES = ("player", "weapons", "mobs", "maps", "projectiles")

def reload_data():
    for n in DATA_FILES:
        CFG[n] = json.loads((DATA / f"{n}.json").read_text(encoding="utf-8"))
    # карты: data/maps/<id>.json, файлы на "_" (заготовки) не читаются
    CFG["map_defs"], CFG["map_errors"] = {}, []
    for f in sorted((DATA / "maps").glob("*.json")):
        if f.stem.startswith("_"): continue
        try: CFG["map_defs"][f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e: CFG["map_errors"].append(f"{f.name} не читается: {e}")
reload_data()
try: SETTINGS = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
except Exception: SETTINGS = {}

def sign(v): return (v > 0) - (v < 0)
def approach(v, t, d): return min(v + d, t) if v < t else max(v - d, t)
def tile(g, c, r): return g[r][c] if 0 <= c < COLS and 0 <= r < ROWS else "."
def solid(g, c, r): return tile(g, c, r) in "#D"
def free(g, r):
    return not any(solid(g, c, y) for c in range(r.left // T, (r.right - 1) // T + 1)
                   for y in range(r.top // T, (r.bottom - 1) // T + 1))

def floor_below(g, x, y):
    """Y верхней кромки первого пола (стена или платформа) под точкой (x, y). Нет пола -> None."""
    c = int(x // T)
    for r in range(max(0, int(y // T)), ROWS):
        if tile(g, c, r) in "#D=" and not solid(g, c, r - 1): return r * T
    return None

def circle_hits_rect(x, y, radius, rect):
    """Касается ли круг прямоугольника (ближайшая точка прямоугольника к центру внутри круга)."""
    nx = min(max(x, rect.left), rect.right); ny = min(max(y, rect.top), rect.bottom)
    return (nx - x) ** 2 + (ny - y) ** 2 <= radius * radius

class FX:
    def __init__(s): s.shake = s.stop = 0; s.items = []
    def text(s, t, x, y): s.items.append(["t", x, y, t, .7])
    def ring(s, x, y, r): s.items.append(["r", x, y, r, .25])

class Body:
    def __init__(s, x, y, w, h):
        s.x, s.y, s.w, s.h = x, y, w, h; s.vx = s.vy = 0.0; s.ground = False; s.wall = 0
    @property
    def rect(s): return pg.Rect(int(s.x), int(s.y), s.w, s.h)
    @property
    def cx(s): return s.x + s.w / 2
    @property
    def cy(s): return s.y + s.h / 2
    def move(s, g, dt, drop=False):
        s.wall = 0; s.x += s.vx * dt; r = s.rect
        for c in range(r.left // T, (r.right - 1) // T + 1):
            for y in range(r.top // T, (r.bottom - 1) // T + 1):
                if solid(g, c, y):
                    if s.vx > 0: s.x = c * T - s.w; s.wall = 1
                    elif s.vx < 0: s.x = (c + 1) * T; s.wall = -1
                    s.vx = 0; r = s.rect
        ob = s.y + s.h; s.y += s.vy * dt; s.ground = False; r = s.rect
        for c in range(r.left // T, (r.right - 1) // T + 1):
            for y in range(r.top // T, (r.bottom - 1) // T + 1):
                t = tile(g, c, y); sol = t in "#D"
                plat = t == "=" and s.vy >= 0 and not drop and ob <= y * T + 1
                if sol and s.vy < 0: s.y = (y + 1) * T; s.vy = 0; r = s.rect
                elif (sol or plat) and s.vy >= 0: s.y = y * T - s.h; s.vy = 0; s.ground = True; r = s.rect
