"""Чекпоинты — гранёные бирюзовые кристаллы (символ O в общей легенде карт data/maps.json).

Клетка чекпоинта физически пустая: "O": {"type": "empty", "checkpoint": true}. Собирает их
maps.GameMap.__init__ (checkpoint.collect). Когда герой входит в клетку кристалла:
  • здоровье и мана восстанавливаются до максимума;
  • кристалл становится точкой возрождения: pl.cp = (id карты, x, земля);
  • в одиночной игре делается автосохранение забега (save_io.autosave, ленивый импорт;
    функция появится отдельно — ошибки пишутся в консоль, игра не падает);
  • повторная активация того же кристалла 2 секунды «остывает» и ничего не делает.
Смерть в одиночной игре (respawn, зовётся из main.step вместо старого раннего выхода при
pl.hp <= 0) возвращает героя к последнему кристаллу — живым и с полной маной. Сразу после
возрождения герой freeze_time() секунд «заморожен» (штраф смерти): неподвижен (ввод отключён —
в main.step ему идёт mp.NO_KEYS, как замороженным игрокам хоста мультиплеера), неуязвим
(pl.inv держится на уровне pl.frozen — тик делают tick/freeze) и рисуется бирюзовым кристаллом (draw_crystal).

Вызовы снаружи (main.py / multiplayer.py):
  update(g, dt)                    — тик одиночной игры: заморозка + активация при касании
  respawn(g)                       — смерть в одиночке: назад к кристаллу
  draw_room(v, r, t_ms, pl)        — кристаллы текущей комнаты (main.draw)
  draw_crystal(v, pl, t_ms)        — кристалл вокруг замороженного героя (main.draw)
  activate / tick / freeze         — то же по игрокам для хоста мультиплеера

Настройки: data/settings.json -> "checkpoint_freeze_seconds" — сколько секунд герой стоит
кристаллом после возрождения (по умолчанию 10, зажимается в 0..120). Новых JSON не нужно.
"""
import math
import pygame as pg
from core import CFG, SETTINGS, T
from anim import sprite, ASSETS_EXISTS

COLOR = (110, 225, 255)   # бирюза кристалла
REST_MS = 2000            # «остывание» кристалла после активации, мс
CRYST_H = 44              # высота кристалла над землёй, px


def freeze_time():
    """Сколько секунд герой стоит кристаллом после возрождения (SETTINGS, зажато в 0..120)."""
    try: t = float(SETTINGS.get("checkpoint_freeze_seconds", 10.0))
    except (TypeError, ValueError): t = 10.0
    return max(0.0, min(120.0, t))


def collect(r):
    """Клетки-кристаллы карты (легенда: checkpoint) -> [{"rect", "x", "ground"}]. Зовёт maps.GameMap."""
    out = []
    for c, row, e in r.cells():
        if e.get("checkpoint"):
            out.append({"rect": pg.Rect(c * T, row * T, T, T), "x": c * T + T / 2, "ground": (row + 1) * T})
    return out


def activate(g, pl, r, cp, fx=None):
    """Герой коснулся кристалла: полное здоровье и мана, точка возрождения, автосохранение (одиночка).
    fx — куда написать подсказку (хост мультиплеера передаёт FX комнаты игрока; None — g.fx)."""
    now = pg.time.get_ticks()
    if cp.get("until") and now < cp["until"]: return   # кристалл ещё «остывает» — не спамим текстом и сейвами
    cp["until"] = now + REST_MS
    pl.cp = (r.id, int(cp["x"]), int(cp["ground"]))
    pl.hp = pl.maxhp
    pl.refresh_mana(True)
    pl.mana = pl.maxmana
    (fx if fx is not None else g.fx).text("Чекпоинт: здоровье и мана восстановлены", cp["x"], cp["ground"] - 60)
    if getattr(g, "net", None) is None:   # в сети сейв недоступен: мир считает хост, файлы не пишем
        import save_io   # лениво: save_io импортирует maps, здесь всё уже загружено
        try: save_io.autosave(g)
        except Exception as e: print("[чекпоинт] не удалось сохранить:", e)


def update(g, dt):
    """Тик одиночной игры (зовёт main.step): заморозка героя + активация кристалла, в которого он вошёл."""
    pl = g.pl
    tick(pl, dt)
    if pl.hp <= 0: return
    for cp in getattr(g.room, "checkpoints", ()):
        if pl.rect.colliderect(cp["rect"]):
            activate(g, pl, g.room, cp)
            break


def tick(pl, dt):
    """Тик кристалла возрождения: заморозка тает; пока длится — герой неуязвим (inv >= frozen)."""
    pl.frozen = max(0.0, getattr(pl, "frozen", 0.0) - dt)
    pl.inv = max(pl.inv, pl.frozen)


def freeze(pl, seconds=None):
    """Заморозить героя (после возрождения): неуязвим и стоит кристаллом seconds секунд."""
    pl.frozen = float(seconds or freeze_time())
    pl.inv = max(pl.inv, pl.frozen)


def respawn(g):
    """Смерть в одиночной игре: вернуться к последнему кристаллу (или к точке входа в комнату)."""
    if getattr(g, "net", None) is not None: return   # в сети смертью занимается хост (multiplayer.py)
    pl = g.pl
    cp = getattr(pl, "cp", None)
    if cp and cp[0] in CFG["map_defs"]:   # карта кристалла существует в данных мира
        g.go(cp[0], None)                 # та же комната — просто перезайдём
        pl.vx = pl.vy = 0.0
        pl.x = cp[1] - pl.w / 2
        pl.y = cp[2] - pl.h               # ноги на землю кристалла
        if pl.h != pl.H0:                 # подрезать высоту, как делает g.place (герой мог погиб в перекате)
            pl.y -= pl.H0 - pl.h
            pl.h = pl.H0
    else:                                 # кристалла ещё не было — точка появления в текущей комнате
        g.place(*g.respawn)
    pl.hp = pl.maxhp
    pl.refresh_mana(True)
    pl.mana = pl.maxmana
    freeze(pl)                            # кристалл возрождения: неуязвимость на freeze_time()
    pl.atk = None; pl.skill_cast = None; pl.shield_time = 0.0; pl.shield_hp = 0.0; pl.hitbox = None
    pl.grab = None; pl.channel = None; pl.hold = None; pl.stun = 0
    g.fx.text("Ты погиб — возвращение к чекпоинту", pl.cx, pl.y - 40)


# ---------- отрисовка ----------

def _crystal_points(x, ground):
    """Вершины гранёного кристалла: шестиугольник от земли (ground) вверх на CRYST_H."""
    return [(x, ground - CRYST_H), (x - 10, ground - CRYST_H + 13), (x - 10, ground - 9),
            (x, ground), (x + 10, ground - 9), (x + 10, ground - CRYST_H + 13)]


def draw_room(v, r, t_ms, pl=None):
    """Кристаллы комнаты (зовёт main.draw). Пульсация яркости по t_ms; у текущей точки
    возрождения героя (pl.cp совпал) — ярче и со свечением. Если есть картинка
    assets/icons/checkpoint.png — она рисуется вместо полигональной заглушки."""
    img = sprite("icons/checkpoint.png", 30, CRYST_H) if ASSETS_EXISTS("icons/checkpoint.png") else None
    for cp in getattr(r, "checkpoints", ()):
        x, ground = int(cp["x"]), int(cp["ground"])
        active = pl is not None and getattr(pl, "cp", None) == (r.id, int(cp["x"]), int(cp["ground"]))
        pulse = 0.5 + 0.5 * math.sin(t_ms / 350.0 + cp["x"] * 0.013)   # фаза чуть плывёт между кристаллами
        if active:   # мягкое свечение вокруг активного кристалла
            rad = int(30 + 8 * pulse)
            halo = pg.Surface((rad * 2, rad * 2), pg.SRCALPHA)
            pg.draw.circle(halo, (*COLOR, 55), (rad, rad), rad)
            v.blit(halo, (x - rad, ground - CRYST_H // 2 - rad))
        if img:   # авторская картинка вместо заглушки (чуть покачивается)
            v.blit(img, (x - img.get_width() // 2, ground - CRYST_H - 2 + int(3 * pulse)))
            continue
        k = (0.85 + 0.15 * pulse) * (1.25 if active else 1.0)
        col = lambda m: tuple(min(255, int(c * k * m)) for c in COLOR)
        pts = _crystal_points(x, ground)
        pg.draw.polygon(v, col(1.0), pts)
        pg.draw.polygon(v, col(1.6), pts, 2)
        # грани: линии от вершин к противоположным бокам
        pg.draw.line(v, col(1.35), pts[0], pts[2])
        pg.draw.line(v, col(1.35), pts[0], pts[4])
        pg.draw.line(v, col(0.6), pts[3], pts[1])
        pg.draw.line(v, col(0.6), pts[3], pts[5])


def draw_crystal(v, pl, t_ms):
    """Замороженный герой (только что возродился): полупрозрачный бирюзовый кристалл-ромб,
    охватывающий его хитбокс: пульс альфы, грань-блик, редкие искры."""
    if getattr(pl, "frozen", 0.0) <= 0: return
    r = pl.rect.inflate(16, 12)
    a = int(110 + 45 * (0.5 + 0.5 * math.sin(t_ms / 140.0)))   # пульс прозрачности
    ov = pg.Surface(v.get_size(), pg.SRCALPHA)
    cx, cy = r.centerx, r.centery
    pts = [(cx, r.top), (r.right, cy), (cx, r.bottom), (r.left, cy)]
    pg.draw.polygon(ov, (*COLOR, a), pts)
    pg.draw.polygon(ov, (*COLOR, min(255, a + 70)), pts, 2)
    pg.draw.line(ov, (255, 255, 255, min(255, a + 60)), (cx, r.top + 3), (r.left + 3, cy))   # блик на грани
    for i in range(3):   # искры стекают по граням одна за другой
        ph = (t_ms / 900.0 + i / 3.0) % 1.0
        sx = cx + math.sin(t_ms / 500.0 + i * 2.1) * (r.width // 2 + 5)
        sy = r.top + ph * r.height
        pg.draw.circle(ov, (*COLOR, int(200 * (1 - abs(2 * ph - 1)))), (int(sx), int(sy)), 2)
    v.blit(ov, (0, 0))
