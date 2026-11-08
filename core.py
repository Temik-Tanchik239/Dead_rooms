"""Общее для всех модулей: пути, конфиги из data/*.json, размеры поля, физическое тело, мелкие функции."""
import copy, json, sys
from contextlib import contextmanager
from pathlib import Path
import pygame as pg

# В обычном запуске ресурсы лежат рядом с исходниками. В сборке PyInstaller --onefile
# они распаковываются во временную папку sys._MEIPASS. Если рядом с EXE есть папки
# data/assets, используем их: так игрок может редактировать JSON и настройки.
FROZEN = bool(getattr(sys, "frozen", False))
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
RESOURCE_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATA = (BASE / "data") if (BASE / "data").is_dir() else (RESOURCE_BASE / "data")
ASSETS = (BASE / "assets") if (BASE / "assets").is_dir() else (RESOURCE_BASE / "assets")
T, COLS, ROWS = 32, 50, 50      # размер карты в клетках: 50 x 50
MW, MH = COLS * T, ROWS * T      # размер карты в пикселях
VIEW_H = 16 * T                  # высота игрового окна (камера показывает кусок карты)
W, H = 30 * T, VIEW_H            # размер окна; HUD рисуется прямо поверх игрового поля (панель прозрачная)
CFG = {}
DATA_FILES = ("player", "weapons", "mobs", "maps", "projectiles", "skills")

def reload_data():
    for n in DATA_FILES:
        CFG[n] = json.loads((DATA / f"{n}.json").read_text(encoding="utf-8"))
    # Настройки босса и оформления полосы HP вынесены в assets/boss/boss.json.
    # Их можно менять без правки Python-кода; моб босса добавляется в общий каталог мобов.
    CFG["boss"] = read_json(ASSETS / "boss" / "boss.json", {})
    boss_mob = CFG["boss"].get("mob", {}) if isinstance(CFG["boss"], dict) else {}
    if boss_mob:
        CFG["mobs"]["__boss__"] = copy.deepcopy(boss_mob)
        CFG["mobs"]["__boss__"]["boss"] = True
        CFG["mobs"]["__boss__"]["name"] = CFG["boss"].get("name", "Босс")
    # Внешность и размеры тренировочного манекена (F6) — assets/dummy/dummy.json, см. devtools.py. Файл необязателен.
    CFG["dummy"] = read_json(ASSETS / "dummy" / "dummy.json", {})
    # Общие настройки невидимости (процент прозрачности, плавность, мигание) — data/invisibility.json, см. invisibility.py. Файл необязателен.
    CFG["invisibility"] = read_json(DATA / "invisibility.json", {})
    # Настраиваемое дерево навыков хранится в assets/skill_tree.json.
    try:
        CFG["skill_tree"] = json.loads((ASSETS / "skill_tree.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        CFG["skill_tree"] = {"lock_icon": "icons/skill_locked.png", "grid_columns": 4, "grid_rows": 2,
                             "slots": [{"skill": sid, "unlock_level": int(d.get("unlock_level", i + 1))}
                                       for i, (sid, d) in enumerate(CFG.get("skills", {}).items())][:8]}
    # Оформление меню навыков: размеры, цвета, тексты и изображения — assets/skill_menu.json.
    try:
        CFG["skill_menu"] = json.loads((ASSETS / "skill_menu.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        CFG["skill_menu"] = {}
    # карты: data/maps/<id>.json, файлы на "_" (заготовки) не читаются
    CFG["map_defs"], CFG["map_errors"] = {}, []
    for f in sorted((DATA / "maps").glob("*.json")):
        if f.stem.startswith("_"): continue
        try: CFG["map_defs"][f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e: CFG["map_errors"].append(f"{f.name} не читается: {e}")
    # Игровая сетка должна вмещать самую большую карту, а не обрезать её
    # по старому фиксированному размеру 50x50. Маленькие карты дополняются пустотой.
    global COLS, ROWS, MW, MH
    map_rows = [md.get("rows", []) for md in CFG["map_defs"].values()]
    COLS = max([50] + [len(row) for rows in map_rows for row in rows if isinstance(row, str)])
    ROWS = max([50] + [len(rows) for rows in map_rows if isinstance(rows, list)])
    MW, MH = COLS * T, ROWS * T
    # Персонажи: data/characters.json (необязателен) + внешний вид из assets/characters/<id>/character.json.
    CFG["player_base"], CFG["skills_base"], CFG["weapons_base"] = CFG["player"], CFG["skills"], CFG["weapons"]
    CFG["skill_tree_base"], CFG["skill_menu_base"] = CFG["skill_tree"], CFG["skill_menu"]
    CFG["characters"] = read_json(DATA / "characters.json", {})
    CFG["char_looks"] = {cid: read_json(ASSETS / char_folder(cid) / "character.json", {}) for cid in char_ids()}
    CFG["char_menus"] = {cid: read_json(ASSETS / char_folder(cid) / "skill_menu.json", {}) for cid in char_ids()}
    _PCFG.clear(); _VIEWS.clear()
    apply_character(CHAR["id"])

# ---------------- ПЕРСОНАЖИ ----------------
CHAR = {"id": None}   # id выбранного персонажа
_PCFG = {}
_VIEWS = {}           # кэш готовых наборов CFG для каждого героя (мультиплеер: несколько героев сразу)
_VIEW_KEYS = ("player", "skills", "weapons", "skill_tree", "skill_menu", "character")

def deep_merge(a, b):
    """Копия словаря a, поверх которой рекурсивно записан b (вложенные словари сливаются, остальное заменяется)."""
    out = copy.deepcopy(a) if isinstance(a, dict) else {}
    for k, v in (b or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out

def read_json(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except OSError: return default
    except ValueError as e: print("ошибка в", path, e); return default

def char_ids():
    """id персонажей в порядке order из data/characters.json."""
    data = CFG.get("characters", {}); chars = data.get("characters", {})
    order = [c for c in data.get("order", []) if c in chars]
    return order + [c for c in chars if c not in order]

def char_def(cid): return CFG.get("characters", {}).get("characters", {}).get(cid, {})
def char_folder(cid): return char_def(cid).get("assets", f"characters/{cid}")
def char_look(cid): return CFG.get("char_looks", {}).get(cid, {})

def char_player_cfg(cid):
    """player.json + stats персонажа + внешний вид из assets (character.json)."""
    if cid not in _PCFG:
        _PCFG[cid] = deep_merge(deep_merge(CFG["player_base"], char_def(cid).get("stats", {})), char_look(cid))
    return _PCFG[cid]

def apply_character(cid=None):
    """Сделать персонажа текущим: CFG["player"], ["skills"], ["weapons"], ["skill_tree"], ["skill_menu"] — уже с его правками."""
    ids = char_ids()
    if cid not in ids: cid = CFG.get("characters", {}).get("default") if CFG.get("characters", {}).get("default") in ids else (ids[0] if ids else None)
    CHAR["id"] = cid; c = char_def(cid)
    CFG["player"] = char_player_cfg(cid) if cid else CFG["player_base"]
    CFG["skills"] = deep_merge(CFG["skills_base"], c.get("skill_overrides", {}))
    CFG["weapons"] = deep_merge(CFG["weapons_base"], c.get("weapon_overrides", {}))
    tree = c.get("skill_tree")
    if isinstance(tree, list): tree = {"slots": tree}
    CFG["skill_tree"] = deep_merge(CFG["skill_tree_base"], tree or {})
    CFG["skill_menu"] = deep_merge(CFG["skill_menu_base"], CFG.get("char_menus", {}).get(cid, {}))
    CFG["character"] = {**c, "id": cid}
    return cid

def _set_char(cid):
    """Быстро переключить CFG на героя cid (без повторного слияния JSON)."""
    if cid not in _VIEWS:
        real = apply_character(cid)
        view = (real, {k: CFG[k] for k in _VIEW_KEYS})
        _VIEWS[cid] = view; _VIEWS.setdefault(real, view)
    real, view = _VIEWS[cid]
    CFG.update(view); CHAR["id"] = real

@contextmanager
def use_char(cid):
    """with use_char("knight"): ... — внутри блока CFG["player"], ["weapons"], ["skills"] ... принадлежат этому герою.
    Нужно в мультиплеере: у каждого игрока свой персонаж, а данные героя лежат в общем CFG."""
    prev = CHAR["id"]
    if cid is None or cid == prev:
        yield; return
    _set_char(cid)
    try: yield
    finally: _set_char(prev)

reload_data()
try: SETTINGS = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
except Exception: SETTINGS = {}

def sign(v): return (v > 0) - (v < 0)
def approach(v, t, d): return min(v + d, t) if v < t else max(v - d, t)
def tile(g, c, r):
    # Проверяем размеры самой сетки: разные карты могут иметь разную ширину/высоту.
    return g[r][c] if 0 <= r < len(g) and 0 <= c < len(g[r]) else "."
def solid(g, c, r): return tile(g, c, r) in "#D"
def free(g, r):
    return not any(solid(g, c, y) for c in range(r.left // T, (r.right - 1) // T + 1)
                   for y in range(r.top // T, (r.bottom - 1) // T + 1))

def floor_below(g, x, y):
    """Y верхней кромки первого пола (стена или платформа) под точкой (x, y). Нет пола -> None."""
    c = int(x // T)
    for r in range(max(0, int(y // T)), len(g)):
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
    # Эффекты заклинаний. data — JSON-дружелюбные списки/числа (сериализуются в мультиплеере).
    def beam(s, x1, y1, x2, y2, col=(170, 210, 255)): s.items.append(["beam", x1, y1, [x2, y2, list(col)[:3]], .22])
    def bolt(s, x, y, col=(200, 230, 255)): s.items.append(["bolt", x, y, list(col)[:3], .3])
    def flash(s, x, y, r, col=(255, 255, 255)): s.items.append(["flash", x, y, [r, list(col)[:3]], .25])

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
