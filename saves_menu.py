"""Экран «Сохранения» главного меню: список забегов + выбор героя для продолжения.

Роутинг из main.py — как у мультиплеера (mp.MENU_MODES = ("mp", "connect")):
  key()        → menu_key(g, k)   при g.menu_mode in MODES
  event()      → menu_event(g, e)
  draw_menu()  → draw_menu(g)     (курсор мыши рисует сам main.draw_menu)

Экран двушаговый:
  g.menu_mode == "saves"       — вертикальный список сохранений (имя, время, круг, герои и уровни);
  g.menu_mode == "saves_char"  — герои выбранного забега; Enter продолжает забег этим героем.

Список сохранений даёт save_io.list_saves(), загрузка — save_io.restore(g, save_id).
Оба импортируются ЛЕНИВО внутри функций: пока save_io.py не появился, экран просто
показывает «Нет сохранений» (для тестов список подставляется в saves_menu._load_saves).

Запись сохранения — объект или dict; поля читаются и с самой записи, и из rec.meta:
  id        — уникальный идентификатор (g.menu_selected синхронизируется с ним);
  name      — имя забега (нет — «Сохранение N»);
  time      — время сохранения (число = timestamp → «ДД.ММ.ГГГГ ЧЧ:ММ»);
  loop      — круг забега (в данных 0 = первый круг, на экране показываем loop+1);
  chars     — список id героев забега;
  level     — {id героя: уровень};
  char      — id героя, которым играли последним.
"""
import pygame as pg
from datetime import datetime

from core import W, VIEW_H, SETTINGS, char_def, char_look

MODES = ("saves", "saves_char")   # роутинг главного агента: if g.menu_mode in saves_menu.MODES

# ---------------- геометрия (окно 960x512: W = 30*T, VIEW_H = 16*T) ----------------
PANEL_W = 700
PANEL_TOP = 78                    # панель от 78 до VIEW_H-64; под ней — строка подсказки
PANEL_BOTTOM_MARGIN = 64
ROW_H = 42                        # высота строки вместе с зазором
ROW_VISIBLE = 8                   # видимых строк в панели, дальше — прокрутка
ROW_INSET = 12                    # отступ строк от краёв панели

COL_TITLE = (255, 220, 130)       # как у заголовков мультиплеера
COL_TEXT = (245, 243, 252)
COL_SUB = (168, 170, 196)
COL_GOLD = (255, 214, 120)        # выделение: уровень, «играл последним»
COL_FRAME = (110, 100, 150)       # рамка панели/строк, как у _button мультиплеера
COL_FRAME_HOV = (200, 180, 255)
COL_FRAME_SEL = (255, 214, 120)

_BACK = "start"                   # куда ведёт Esc из списка сохранений (поле модуля; open_saves(g, back=...))
_ST = {"saves": [], "idx": 0, "scroll": 0, "save_id": None}   # кэш списка + выделение + прокрутка

_FONTS = {}


def _font(size):
    """Шрифт того же семейства, что у main/characters (жирный Arial)."""
    size = int(size)
    if size not in _FONTS:
        _FONTS[size] = pg.font.SysFont("arial,dejavusans,freesans", size, bold=True)
    return _FONTS[size]


def _text(scr, s, size, color, center=None, topleft=None, right=None, shadow=True):
    """Текст с тенью; right — правая граница (выравнивание вправо)."""
    f, txt = _font(size), str(s)
    r = pg.Rect(0, 0, *f.size(txt))
    if center is not None: r.center = (int(center[0]), int(center[1]))
    elif topleft is not None: r.topleft = (int(topleft[0]), int(topleft[1]))
    if right is not None: r.right = int(right)
    if shadow: scr.blit(f.render(txt, True, (0, 0, 0)), r.move(1, 2))
    scr.blit(f.render(txt, True, color), r)
    return r


# ---------------- доступ к записи сохранения (объект или dict, с meta или без) ----------------
def _get(rec, key, default=None):
    for obj in (rec, getattr(rec, "meta", None)):
        if obj is None: continue
        if isinstance(obj, dict):
            if obj.get(key) is not None: return obj[key]
        else:
            v = getattr(obj, key, None)
            if v is not None: return v
    return default


def _fmt_time(v):
    if v is None or v == "": return ""
    if isinstance(v, (int, float)):
        try: return datetime.fromtimestamp(v).strftime("%d.%m.%Y %H:%M")
        except (OSError, OverflowError, ValueError): return str(v)
    return str(v)


def _save_name(rec, i):
    return str(_get(rec, "name") or f"Сохранение {i + 1}")


def _hero_name(cid):
    return str(char_def(cid).get("name") or cid)


def _hero_color(cid):
    try: return tuple(int(c) for c in char_look(cid).get("color", char_def(cid).get("color", [200, 180, 120]))[:3])
    except (TypeError, ValueError): return (200, 180, 120)


# ---------------- данные экрана ----------------
def _load_saves():
    """Свежий список сохранений (ленивый импорт save_io — его пишет параллельный агент).

    Для UI-тестов подменяется целиком: saves_menu._load_saves = lambda: [...].
    """
    try:
        from save_io import list_saves
    except ImportError as e:
        print("saves_menu: save_io недоступен:", e)
        return []
    try:
        return list(list_saves() or [])
    except Exception as e:
        print("saves_menu: list_saves упал:", e)
        return []


def _find_save(sid):
    for rec in _ST["saves"]:
        if _get(rec, "id") == sid: return rec
    return None


def _rows(g):
    """Пункты текущего экрана: сохранения (+НАЗАД) или герои забега (+НАЗАД)."""
    if g.menu_mode == "saves":
        rows = [{"kind": "save", "id": _get(rec, "id", f"save{i}"), "rec": rec} for i, rec in enumerate(_ST["saves"])]
    else:
        rec = _find_save(_ST.get("save_id"))
        chars = _get(rec, "chars", []) or []
        rows = [{"kind": "hero", "cid": cid, "rec": rec} for cid in chars]
    rows.append({"kind": "back"})
    return rows


def _select(g, idx):
    """Выделить строку idx и подогнать окно прокрутки."""
    rows = _rows(g)
    idx = max(0, min(len(rows) - 1, idx))
    _ST["idx"] = idx
    if idx < _ST["scroll"]: _ST["scroll"] = idx
    elif idx >= _ST["scroll"] + ROW_VISIBLE: _ST["scroll"] = idx - ROW_VISIBLE + 1
    if rows:
        it = rows[idx]
        g.menu_selected = str(it.get("id") or it.get("cid") or "back")


def _move(g, d):
    n = len(_rows(g))
    if n: _select(g, (_ST["idx"] + d) % n)   # по кругу


def _scroll(g, d):
    """Колесо/страницы: сдвинуть окно просмотра, выделение держать видимым."""
    rows = _rows(g)
    if len(rows) <= ROW_VISIBLE: return
    _ST["scroll"] = max(0, min(len(rows) - ROW_VISIBLE, _ST["scroll"] + d))
    if _ST["idx"] < _ST["scroll"]: _select(g, _ST["scroll"])
    elif _ST["idx"] >= _ST["scroll"] + ROW_VISIBLE: _select(g, _ST["scroll"] + ROW_VISIBLE - 1)


# ---------------- открытие/закрытие ----------------
def open_saves(g, back=None):
    """Открыть экран «Сохранения» (кнопку добавит главный агент в main.menu_layout/MENU_BUTTONS).
    back — куда вернёт Esc из списка сохранений (по умолчанию: пауза, если открыли из неё, иначе старт-меню)."""
    global _BACK
    if getattr(g, "net", None):
        print("saves_menu: в сетевой игре сохранения недоступны"); return
    _BACK = back or ("pause" if getattr(g, "menu_mode", None) == "pause" else "start")
    _ST["saves"] = _load_saves()        # перечитать список с диска
    _ST["idx"] = 0; _ST["scroll"] = 0; _ST["save_id"] = None
    g.menu_selected = str(_get(_ST["saves"][0], "id", "")) if _ST["saves"] else "back"
    g.menu_mode = "saves"


def _close(g):
    """Esc из списка сохранений: назад туда, откуда открыли (start/pause)."""
    g.menu_mode = _BACK if _BACK in ("start", "pause") else "start"


def _back_to_saves(g):
    """Esc из выбора героя: назад к списку сохранений, выделение — на прежнем сохранении."""
    g.menu_mode = "saves"
    sid = _ST.get("save_id")
    rows = _rows(g)
    idx = next((i for i, it in enumerate(rows) if it["kind"] == "save" and it.get("id") == sid), 0)
    _select(g, idx)


def _open_heroes(g, sid):
    """Enter на сохранении: экран героев этого забега."""
    _ST["save_id"] = sid
    _ST["idx"] = 0; _ST["scroll"] = 0
    g.menu_mode = "saves_char"
    _select(g, 0)


def _restore(g):
    """Enter на герое: продолжить забег. save_io.restore сам выставит героя сохранения."""
    if getattr(g, "net", None):
        print("saves_menu: загрузка сохранения в сетевой игре недоступна"); return
    sid = _ST.get("save_id")
    try:
        from save_io import restore
    except ImportError as e:
        print("saves_menu: save_io недоступен:", e); return
    g.menu_mode = None                  # контракт: меню закрыть ДО restore
    try:
        restore(g, sid)
    except Exception as e:
        print("saves_menu: не удалось загрузить сохранение:", e)
        g.menu_mode = "saves"           # не бросаем игрока в сломанный мир — остаёмся на экране
        return
    g.menu_mode = None                  # контракт: после restore меню тоже закрыто
    pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))


def _activate(g):
    rows = _rows(g)
    if not rows or not (0 <= _ST["idx"] < len(rows)): return
    it = rows[_ST["idx"]]
    if it["kind"] == "back":
        _back_to_saves(g) if g.menu_mode == "saves_char" else _close(g)
    elif it["kind"] == "save":
        _open_heroes(g, it["id"])
    else:
        _restore(g)


# ---------------- ввод ----------------
def menu_key(g, k):
    """W/S/Up/Down — выбор, PageUp/PageDown и Home/End — прокрутка, Enter — открыть, Esc — назад."""
    if g.menu_mode not in MODES: return
    if k in (pg.K_UP, pg.K_w): _move(g, -1)
    elif k in (pg.K_DOWN, pg.K_s): _move(g, 1)
    elif k == pg.K_PAGEUP: _move(g, -ROW_VISIBLE)
    elif k == pg.K_PAGEDOWN: _move(g, ROW_VISIBLE)
    elif k == pg.K_HOME: _select(g, 0)
    elif k == pg.K_END: _select(g, len(_rows(g)) - 1)
    elif k in (pg.K_RETURN, pg.K_KP_ENTER): _activate(g)
    elif k == pg.K_ESCAPE:
        _back_to_saves(g) if g.menu_mode == "saves_char" else _close(g)


def _panel():
    return pg.Rect((W - PANEL_W) // 2, PANEL_TOP, PANEL_W, VIEW_H - PANEL_TOP - PANEL_BOTTOM_MARGIN)


def _row_rect(i):
    p = _panel()
    return pg.Rect(p.x + ROW_INSET, p.y + 14 + i * ROW_H, p.w - ROW_INSET * 2, ROW_H - 4)


def _row_at(g, pos):
    """Индекс строки под курсором (или None) с учётом прокрутки."""
    rows = _rows(g); sc = _ST["scroll"]
    for i in range(sc, min(sc + ROW_VISIBLE, len(rows))):
        if _row_rect(i).collidepoint(pos): return i
    return None


def menu_event(g, e):
    """Мышь: клик по пункту открывает его, наведение выделяет, колесо прокручивает список."""
    if g.menu_mode not in MODES: return
    if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
        i = _row_at(g, e.pos)
        if i is not None:
            _select(g, i); _activate(g)
    elif e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5):     # колесо (старые события)
        _scroll(g, -1 if e.button == 4 else 1)
    elif e.type == pg.MOUSEWHEEL and e.y:                          # колесо (pygame ≥2)
        _scroll(g, -e.y)
    elif e.type == pg.MOUSEMOTION:
        i = _row_at(g, e.pos)
        if i is not None and i != _ST["idx"]: _select(g, i)        # наведение = выбор


# ---------------- отрисовка ----------------
def _row_save(scr, r, it, i):
    rec = it["rec"]
    sel = i == _ST["idx"]
    _text(scr, _save_name(rec, i), 16, COL_TEXT, topleft=(r.x + 10, r.y + 4))
    t = _fmt_time(_get(rec, "time", _get(rec, "date")))
    if t: _text(scr, t, 11, COL_SUB if not sel else COL_GOLD, right=r.right - 10)   # время — вправо
    # строка «круг + герои»
    loop = _get(rec, "loop", 0)
    try: loop_txt = f"Круг {int(loop) + 1}"
    except (TypeError, ValueError): loop_txt = "Круг ?"
    chars = _get(rec, "chars", []) or []
    lv = _get(rec, "level", {}) or {}
    hs = ", ".join(f"{_hero_name(cid)} {lv.get(cid, '?')}" for cid in chars) or "—"
    _text(scr, f"{loop_txt} · Герои: {hs}", 11, COL_SUB, topleft=(r.x + 10, r.y + 23))


def _row_hero(scr, r, it, i):
    cid, rec = it["cid"], it["rec"]
    last = _get(rec, "char") == cid
    _text(scr, _hero_name(cid), 16, _hero_color(cid), topleft=(r.x + 10, r.y + 4))
    lvl = (_get(rec, "level", {}) or {}).get(cid)
    lvl_txt = f"Уровень {lvl}" if lvl is not None else "Уровень ?"
    _text(scr, lvl_txt, 11, COL_GOLD if last else COL_SUB, topleft=(0, 0), right=r.right - 10)
    if last: _text(scr, "играл последним", 11, COL_GOLD, topleft=(r.x + 10, r.y + 23))


def draw_menu(g):
    """Список сохранений ИЛИ список героев выбранного забега. Курсор рисует main.draw_menu."""
    if g.menu_mode not in MODES: return
    scr = g.scr
    # фон как у главного меню: картинка на весь экран + вуаль
    if getattr(g, "menu_background", None):
        scr.blit(pg.transform.smoothscale(g.menu_background, (W, VIEW_H)), (0, 0))
    else:
        scr.fill((8, 8, 17))
    if getattr(g, "menu_veil", None): scr.blit(g.menu_veil, (0, 0))

    heroes = g.menu_mode == "saves_char"
    rec = _find_save(_ST.get("save_id")) if heroes else None
    rows = _rows(g)

    # заголовок и подзаголовок
    t = g.big.render("ГЕРОИ ЗАБЕГА" if heroes else "СОХРАНЕНИЯ", True, COL_TITLE)
    scr.blit(t, t.get_rect(center=(W // 2, 38)))
    if heroes:
        sub = _save_name(rec, 0) if rec else ""
        lv = _get(rec, "level", {}) or {}
        last = _get(rec, "char")
        best = max((v for v in lv.values() if isinstance(v, (int, float))), default=None)
        tail = f" · лучший уровень {int(best)}" if best is not None else ""
        _text(scr, f"«{sub}»{tail}", 12, COL_SUB, center=(W // 2, 66))

    # панель по центру: полупрозрачный тёмный фон (SRCALPHA) + рамка
    panel = _panel()
    overlay = pg.Surface(panel.size, pg.SRCALPHA)
    overlay.fill((10, 10, 22, 205))
    scr.blit(overlay, panel.topleft)
    pg.draw.rect(scr, COL_FRAME, panel, 2, border_radius=10)

    # строки
    mouse = pg.mouse.get_pos()
    sc = _ST["scroll"]
    for i, it in enumerate(rows):
        if not (sc <= i < sc + ROW_VISIBLE): continue
        r = _row_rect(i)
        sel, hov = i == _ST["idx"], r.collidepoint(mouse)
        fill = pg.Surface(r.size, pg.SRCALPHA)
        fill.fill((255, 255, 255, 26 if sel else (14 if hov else 8)))
        scr.blit(fill, r.topleft)
        if sel: pg.draw.rect(scr, COL_FRAME_SEL, r, 2, border_radius=7)
        elif hov: pg.draw.rect(scr, COL_FRAME_HOV, r, 1, border_radius=7)
        if it["kind"] == "save": _row_save(scr, r, it, i)
        elif it["kind"] == "hero": _row_hero(scr, r, it, i)
        else: _text(scr, "НАЗАД", 16, COL_GOLD if sel else COL_TEXT, center=r.center)
    if len(rows) == 1:   # кроме «НАЗАД» нечего показать
        note = "В забеге нет героев" if heroes else "Нет сохранений"
        _text(scr, note, 16, COL_SUB, center=panel.center)

    # полоса прокрутки, если пунктов больше видимых
    if len(rows) > ROW_VISIBLE:
        track = pg.Rect(panel.right - 10, panel.y + 14, 4, ROW_VISIBLE * ROW_H)
        pg.draw.rect(scr, (40, 38, 58), track, border_radius=2)
        th = max(12, int(track.h * ROW_VISIBLE / len(rows)))
        mx = len(rows) - ROW_VISIBLE
        ty = track.y + (track.h - th) * _ST["scroll"] // mx if mx else track.y
        pg.draw.rect(scr, COL_FRAME_SEL, (track.x, ty, track.w, th), border_radius=2)

    # подсказка
    hint = ("Enter — продолжить выбранным героем · Esc — к списку сохранений" if heroes
            else "W/S или ↑/↓ — выбор · Enter — открыть · колесо — прокрутка · Esc — назад")
    _text(scr, hint, 11, (170, 175, 200), center=(W // 2, VIEW_H - 26))
