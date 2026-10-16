"""Текстуры и анимации. У моба один постоянный скин (PNG) + по желанию анимации-серии PNG на отдельные состояния.

Состояния моба: idle, move, jump, windup, attack, recovery, hurt, death.
Где искать кадры (по порядку):
  1) mobs.json -> "anims": {"move": "mobs/rotling/move"} или {"move": {"frames": "...", "fps": 12, "loop": true}}
     "frames" — папка (берутся все *.png по имени: 1.png, 2.png ... 10.png) или шаблон "mobs/rotling/walk_*.png";
  2) если в "anims" путь не указан — папка assets/mobs/<id моба>/<состояние>/ (просто положи туда PNG).
Нет анимации состояния -> берётся запасное (move -> idle, jump -> move ...), в конце — сам скин.
Скорость: "fps" из записи; без fps фазы атаки (windup/attack/recovery) растягиваются ровно на длительность фазы,
остальное идёт с "anim_fps" моба (по умолчанию 10).
"""
import re
import pygame as pg
from core import ASSETS

_IMG, _FRAMES, _ANIM = {}, {}, {}

def clear_cache(): _IMG.clear(); _FRAMES.clear(); _ANIM.clear()

def sprite(path, w, h, flip=False, white=False, angle=0):
    """Текстура из assets/<path>, масштаб под w x h. Нет файла -> None (рисуется заглушка)."""
    key = (path, w, h, flip, white, angle)
    if key not in _IMG:
        img = None
        try:
            img = pg.transform.smoothscale(pg.image.load(str(ASSETS / path)).convert_alpha(), (w, h))
            if flip: img = pg.transform.flip(img, True, False)
            if white: img = pg.mask.from_surface(img).to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
            if angle: img = pg.transform.rotate(img, angle)
        except Exception as e:
            if not (path, "warned") in _IMG: print("текстура не загружена:", path, e)
            _IMG[(path, "warned")] = True
        _IMG[key] = img
    return _IMG[key]

def _natural(p): return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", p.name)]

def frames(path):
    """Список кадров (пути относительно assets) из папки, шаблона *.png или одного файла."""
    if path not in _FRAMES:
        p = ASSETS / path
        if "*" in path: files = sorted(ASSETS.glob(path), key=_natural)
        elif p.is_dir(): files = sorted(p.glob("*.png"), key=_natural)
        elif p.is_file(): files = [p]
        else: files = []
        _FRAMES[path] = [f.relative_to(ASSETS).as_posix() for f in files]
    return _FRAMES[path]

FALLBACK = {"move": "idle", "jump": "move", "windup": "idle", "attack": "idle", "recovery": "idle", "hurt": "idle"}
LOOPING = {"idle", "move", "jump"}
PHASES = {"windup", "attack", "recovery"}

def find_anim(kind, d, state):
    """(кадры, настройки) для состояния моба или None."""
    key = (kind, state)
    if key not in _ANIM:
        spec = d.get("anims", {}).get(state)
        if isinstance(spec, str): spec = {"frames": spec}
        spec = dict(spec or {})
        fr = frames(spec.get("frames") or f"mobs/{kind}/{state}")
        _ANIM[key] = (fr, spec) if fr else None
    return _ANIM[key]

def mob_frame(kind, d, states, t, progress=None):
    """Путь к нужному кадру. states — список имён по приоритету (например ["slam_windup", "windup"]).
    t — сколько секунд моб в этом состоянии, progress — доля пройденной фазы атаки (0..1) или None."""
    chain = list(states)
    while chain[-1] in FALLBACK: chain.append(FALLBACK[chain[-1]])
    for st in chain:
        a = find_anim(kind, d, st)
        if not a: continue
        fr, spec = a; n = len(fr)
        base = states[-1] if st in states else st   # "slam_windup" ведёт себя как windup
        if "fps" in spec: i = int(t * spec["fps"])
        elif progress is not None and base in PHASES: i = int(progress * n)
        else: i = int(t * d.get("anim_fps", 10))
        loop = spec.get("loop", base in LOOPING)
        return fr[i % n] if loop else fr[min(i, n - 1)]
    return d.get("skin") or d.get("sprite") or f"mobs/{kind}.png"

def anim_length(kind, d, state):
    """Длительность анимации без зацикливания (для death), 0 — анимации нет."""
    a = find_anim(kind, d, state)
    if not a: return 0
    fr, spec = a
    return len(fr) / spec.get("fps", d.get("anim_fps", 10))
