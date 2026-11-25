"""Экранные фильтры поверх кадра (ружейный режим рыцаря, «зрение» очков инженера) и прицел мыши.
Свои картинки и анимации — в assets (F5 перезагружает):

ФИЛЬТРЫ:
  assets/filters/<id>/1.png, 2.png, ...  — кадры анимации, зацикливаются; скорость — файл filter.json
                                           ({"fps": 8}) рядом с кадрами, по умолчанию 10;
  assets/filters/<id>/filter.png         — одна статичная картинка вместо анимации;
  assets/filters/<id>.png                — или одиночный файл рядом с папкой;
  нет файлов — процедурная анимация кодом (дыхание по яркости), кадры масштабируются в окно.
Появление фильтра — плавное (0.25 с накат), анимация крутится с первого кадра.

ПРИЦЕЛ (точка прицеливания в игре, когда курсор скрыт):
  assets/characters/<id>/crosshair.png, папка crosshair/ или cursor.png — прицел героя (cursor.png — то же самое);
  assets/ui/crosshair/1.png, ...        или assets/ui/crosshair.png                    — общий прицел;
  прицел героя важнее общего; нет своих файлов — процедурный (кружок с рисками). Картинка больше
  64 px сжимается с сохранением пропорций; точка прицеливания — центр картинки; filter.json задаёт fps.
"""
import json
import re
import pygame as pg
from core import ASSETS, W, VIEW_H
from anim import sprite, image

_CACHE = {}     # fid -> {"frames": [Path], "fps": N}
_XHAIR = {}     # ключ прицела -> {"frames": [Path], "fps": N} | None
_LAST = {}      # fid -> тик последнего кадра, когда фильтр был на экране
_SINCE = {}     # fid -> тик появления (для плавного наката)
FADE = 0.25     # длительность появления, с

def clear_cache(): _CACHE.clear(); _XHAIR.clear()

def _natural(p): return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", p.name)]

def _spec(folder):
    """Кадры и fps из папки: filter.png — статичная картинка, иначе все *.png по имени; fps — filter.json."""
    cfg = {}
    try:
        j = folder / "filter.json"
        if j.is_file(): cfg = json.loads(j.read_text(encoding="utf-8"))
    except Exception: pass
    static = folder / "filter.png"
    if static.is_file(): files = [static]
    else: files = sorted((p for p in folder.glob("*.png") if p.is_file()), key=_natural)
    try: fps = max(1, min(60, int(cfg.get("fps", 10))))
    except (TypeError, ValueError): fps = 10
    return {"frames": files, "fps": fps}

def _find(paths):
    """Первая существующая папка/файл из списка путей -> {"frames", "fps"} или None."""
    for p in paths:
        p = ASSETS / p
        if p.is_dir():
            spec = _spec(p)
            if spec["frames"]: return spec
        elif p.is_file(): return {"frames": [p], "fps": 10}
    return None

def draw(scr, fid, fallback=None, t=None):
    """Рисует фильтр fid: свои кадры из assets/filters/<fid>/ или процедурную анимацию fallback(scr, t, k).
    Появление плавное: k — доля наката (0..1)."""
    t = pg.time.get_ticks() / 1000 if t is None else t
    now = pg.time.get_ticks()
    prev = _LAST.get(fid)
    _LAST[fid] = now
    since = _SINCE.setdefault(fid, now)
    if prev is None or now - prev > 500: _SINCE[fid] = since = now   # фильтр исчезал >0.5 с — накат заново
    k = min(1.0, (now - since) / (FADE * 1000))
    spec = _CACHE.get(fid) or _CACHE.setdefault(fid, _find([f"filters/{fid}", f"filters/{fid}.png"]))
    if spec and spec["frames"]:
        n = len(spec["frames"])
        i = int(t * spec["fps"]) % n if n > 1 else 0
        rel = spec["frames"][i].relative_to(ASSETS).as_posix()
        img = sprite(rel, W, VIEW_H)   # масштаб в окно; кэш anim чистится по F5
        if img:
            if k < 1.0: img = img.copy(); img.set_alpha(int(255 * k))
            scr.blit(img, (0, 0)); return
    if fallback: fallback(scr, t, k)

# ---------------- прицел ----------------
def crosshair(cid=None, t=None):
    """Картинка прицела героя (или None — рисуется процедурный). Анимация крутится, если кадров несколько.
    Свои варианты (по приоритету): assets/characters/<id>/crosshair(.png|/), assets/characters/<id>/cursor.png
    (старое имя — те же кастомные прицелы героев), затем общий assets/ui/crosshair(.png|/)."""
    t = pg.time.get_ticks() / 1000 if t is None else t
    key = cid or ""
    spec = _XHAIR.get(key, "?")
    if spec == "?":
        paths = []
        if cid: paths += [f"characters/{cid}/crosshair", f"characters/{cid}/crosshair.png", f"characters/{cid}/cursor.png"]
        paths += ["ui/crosshair", "ui/crosshair.png"]
        spec = _XHAIR.setdefault(key, _find(paths))
    if not spec: return None
    fr = spec["frames"]; n = len(fr)
    i = int(t * spec["fps"]) % n if n > 1 else 0
    rel = fr[i].relative_to(ASSETS).as_posix()
    raw = image(rel)                       # родный размер (кэш anim, F5 чистит)
    if raw is None: return None
    w, h = raw.get_size()
    if max(w, h) > 64:                     # крупный PNG сжимаем до 64 по большей стороне, пропорции сохраняем
        kk = 64 / max(w, h); w, h = max(1, int(w * kk)), max(1, int(h * kk))
    return sprite(rel, w, h)
