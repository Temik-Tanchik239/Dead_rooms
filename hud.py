"""Нижний левый угол (панель прозрачная, рисуется поверх игры): три квадратные иконки (персонаж, оружие 1 — ЛКМ, оружие 2 — ПКМ) и под иконкой персонажа полоски HP и маны.
Иконки лежат в assets/icons/: player.png и <id оружия>.png; свои пути — поле icon в data/player.json и data/weapons.json.
Нет файла иконки — вместо неё рисуется сам скин. Полоски HP и маны. Всё настраивается в data/player.json: hp_bar и mana.bar.
Вертикальные «книги» у левого края экрана (book_draw): у мага (spellcaster) — колонка заклинаний, у барда (bard) — колонка нот, у арбалетчика
(crossbows — Тень) — две колонки видов снарядов (левая — левый арбалет/ЛКМ, правая — правый/ПКМ): предыдущий (сверху, мелко) · текущий (крупно) · следующий (снизу, мелко); при смене список плавно
прокручивается (book_scroll). Положение и размер — ключ раскладки "book" (F2). У арбалетчика слот навыка Q стоит справа от портрета.
Поля полоски: x, y (от нижнего края окна, минус — вверх), w, h, color, back, border, flash (цвет рамки, когда не хватило маны),
ticks (деление через каждые N единиц, 0 — без делений), text (числа на полоске),
fill_skin / back_skin / frame_skin — картинки из assets (необязательно; нет файла — рисуются цветные прямоугольники)."""
import pygame as pg
import math
from core import CFG, VIEW_H
from anim import sprite
import weapon
import spells
import crossbow
import bard
import inventory
from core import SETTINGS, W

ICON, GAP, ICON_Y = 48, 8, -80  # размер квадрата, отступ между иконками, y иконок от нижнего края окна (минус — вверх)

HP = {"x": 8, "y": -28, "w": 48, "h": 10, "color": [210, 60, 60], "back": [60, 20, 20], "border": [20, 8, 8], "text": False, "ticks": 0}
MP = {"x": 8, "y": -16, "w": 48, "h": 10, "color": [70, 140, 255], "back": [18, 26, 60], "border": [8, 12, 30], "flash": [255, 90, 90], "text": False, "ticks": 20}

def layout():
    """Пользовательская раскладка HUD: координаты от левого верхнего угла."""
    cfg = SETTINGS.setdefault("hud_layout", {})
    defaults = {
        "player": [8, VIEW_H - 80, 48],
        # Оружие и активный навык расположены ниже портрета, в одной нижней линии.
        # Порядок слева направо: оружие ЛКМ, оружие ПКМ, активный навык Q.
        "weapon1": [64, VIEW_H - 56, 48], "weapon2": [120, VIEW_H - 56, 48],
        "skill": [176, VIEW_H - 56, 48],
        "book": [10, 150, 56],   # вертикальные книги заклинаний (маг) / снарядов (Тень) у левого края: x, y верха блока, размер крупной ячейки (масштабирует всё)
        "hp": [8, VIEW_H - 28, 48, 10], "mana": [8, VIEW_H - 16, 48, 10],
    }
    for k, v in defaults.items(): cfg.setdefault(k, v.copy())
    return cfg

def bar(scr, c, value, maxv, y0, flash=False, font=None):
    x, y, w, h = c["x"], y0 + c["y"], c["w"], c["h"];
    key = "hp" if c.get("_layout_key") == "hp" else "mana" if c.get("_layout_key") == "mana" else None
    if key:
        x, y, w, h = layout()[key]
    k = max(0.0, min(1.0, value / maxv)) if maxv else 0.0; fw = round(w * k)
    back = sprite(c["back_skin"], w, h) if c.get("back_skin") else None
    if back: scr.blit(back, (x, y))
    else: pg.draw.rect(scr, c["back"], (x, y, w, h))
    img = sprite(c["fill_skin"], w, h) if c.get("fill_skin") else None
    if fw > 0:
        if img: scr.blit(img, (x, y), pg.Rect(0, 0, fw, h))
        else: pg.draw.rect(scr, c["color"], (x, y, fw, h))
    if c.get("ticks") and maxv:
        for v in range(int(c["ticks"]), int(maxv), int(c["ticks"])):
            tx = x + round(w * v / maxv); pg.draw.line(scr, c["border"], (tx, y), (tx, y + h - 1))
    fr = sprite(c["frame_skin"], w, h) if c.get("frame_skin") else None
    if fr: scr.blit(fr, (x, y))
    else: pg.draw.rect(scr, c["border"], (x, y, w, h), 1)
    if flash: pg.draw.rect(scr, c.get("flash", [255, 90, 90]), (x - 1, y - 1, w + 2, h + 2), 2)
    if c.get("text") and font:
        t = font.render(f"{int(value)}/{int(maxv)}", True, (235, 240, 255)); scr.blit(t, (x + (w - t.get_width()) // 2, y + (h - t.get_height()) // 2))

def draw(scr, pl, font):
    P = CFG["player"]; y0 = VIEW_H
    # Заклинатель (spellcaster в data/characters.json — маг/инженер): портрет + окно из трёх умений вместо иконок оружия.
    if CFG.get("character", {}).get("spellcaster"):
        portrait(scr, pl, font); book_draw(scr, pl, font); weapon_slots(scr, pl, font)   # + оружие в свободной ПКМ, если оно есть
    elif crossbow.enabled() or bard.enabled():   # арбалетчик (Тень) / бард: портрет + колонки у левого края + навык Q рядом с портретом
        portrait(scr, pl, font); book_draw(scr, pl, font)
        sk = layout().get("skill", [176, VIEW_H - 56, 48]); skill_slot(scr, pl, font, [sk[0] + skill_shift(), sk[1], sk[2]])
        weapon_slots(scr, pl, font)   # у барда оружие в свободной ПКМ (если есть)
    else:
        icons(scr, pl, font)
    bar(scr, {**HP, **P.get("hp_bar", {}), "_layout_key": "hp"}, max(0, pl.hp), pl.maxhp, y0)
    bar(scr, {**MP, **P.get("mana", {}).get("bar", {}), "_layout_key": "mana"}, pl.mana, pl.maxmana, y0, pl.mana_flash > 0, font)
    xp_indicator(scr, pl, font)

def xp_indicator(scr, pl, font):
    """Небольшое кольцо опыта, наполовину наложенное на верхний правый угол иконки персонажа."""
    scale = 4  # supersampling для гладкого края кольца
    radius = 13
    ring_w = 2

    # Привязываем индикатор к реальному положению и размеру иконки персонажа,
    # включая пользовательскую раскладку HUD.
    player_rect = layout().get("player", [8, VIEW_H - 80, 48])
    px, py, psize = player_rect[:3]
    cx, cy = int(px + psize), int(py)

    size = (radius * 2 + 8) * scale
    center = size // 2
    outer_r = radius * scale
    inner_r = (radius - ring_w) * scale
    ratio = max(0.0, min(1.0, float(getattr(pl, "xp", 0)) / max(1, float(getattr(pl, "xp_next", 1)))))

    layer = pg.Surface((size, size), pg.SRCALPHA)
    pg.draw.circle(layer, (7, 8, 13, 235), (center, center), outer_r + 3 * scale)
    pg.draw.circle(layer, (64, 48, 26, 255), (center, center), outer_r + scale)
    pg.draw.circle(layer, (201, 157, 72, 255), (center, center), outer_r)
    pg.draw.circle(layer, (19, 18, 22, 255), (center, center), inner_r + scale)

    track_r = radius - 1
    track_rect = pg.Rect(center - track_r * scale, center - track_r * scale,
                         track_r * 2 * scale, track_r * 2 * scale)
    pg.draw.arc(layer, (74, 61, 43, 255), track_rect, 0, math.tau, 2 * scale)
    if ratio > 0:
        pg.draw.arc(layer, (255, 220, 133, 255), track_rect,
                    -math.pi / 2, -math.pi / 2 + ratio * math.tau, 2 * scale)
        pg.draw.arc(layer, (255, 241, 190, 235),
                    pg.Rect(track_rect.x + scale, track_rect.y + scale,
                            track_rect.w - 2 * scale, track_rect.h - 2 * scale),
                    -math.pi / 2, -math.pi / 2 + ratio * math.tau, scale)

    final_size = size // scale
    layer = pg.transform.smoothscale(layer, (final_size, final_size))
    # Центр кольца стоит ровно на углу иконки: половина снаружи, половина поверх портрета.
    scr.blit(layer, (int(cx - final_size / 2), int(cy - final_size / 2)))

    level = str(int(getattr(pl, "level", 1)))
    level_font = pg.font.Font(None, 17 if len(level) < 3 else 13)
    txt = level_font.render(level, True, (255, 239, 190))
    shadow = level_font.render(level, True, (12, 10, 8))
    rect = txt.get_rect(center=(cx, cy))
    scr.blit(shadow, rect.move(1, 1))
    scr.blit(txt, rect)

def label(scr, font, text, x, y, col=(235, 235, 240)):
    scr.blit(font.render(text, True, (0, 0, 0)), (x + 1, y + 1)); scr.blit(font.render(text, True, col), (x, y))

def slot(scr, i, path, fallback, border=(96, 90, 130), layout_key=None, pos=None):
    """Квадрат ICON x ICON номер i слева направо. path — файл иконки в assets, fallback(rect) — чем заменить, если файла нет.
    pos — [x, y, размер], если нужно поставить квадрат в конкретное место (иначе берётся из раскладки layout_key)."""
    cfg = layout()
    pos = pos or (cfg.get(layout_key) if layout_key else None)
    x, y, size = pos if pos else [8 + i * (ICON + GAP), VIEW_H + ICON_Y, ICON]
    r = pg.Rect(int(x), int(y), int(size), int(size)); img = sprite(path, r.w, r.h) if path else None
    if img: scr.blit(img, r)
    else:
        pg.draw.rect(scr, (30, 27, 44), r, border_radius=8); fallback(r); pg.draw.rect(scr, border, r, 2, border_radius=8)
    return r

def portrait(scr, pl, font):
    """Иконка персонажа (слот 0). Кольцо опыта привязано к ней отдельно (xp_indicator)."""
    P = CFG["player"]
    def face(r):
        img = sprite(P.get("skin", "player/idle.png"), 30, 38)
        if img: scr.blit(img, img.get_rect(center=r.center))
    slot(scr, 0, P.get("icon", "icons/player.png"), face, layout_key="player")


def channel_overlay(scr, pl, sid, r, font, color):
    """Индикатор удерживаемого заклинания (skills.json: "channel": true) на иконке навыка sid в прямоугольнике r.
    Пока герой колдует: уже «израсходованное» время затемняет иконку сектором по часовой стрелке (светлая часть = сколько
    ещё можно стоять и колдуть), в центре — оставшиеся секунды, рамка пульсирует цветом заклинания.
    Возвращает True, если индикатор нарисован (тогда кулдаун/«готово» на иконке не рисуем)."""
    ch = getattr(pl, "channel", None)
    if not ch or ch.get("sid") != sid: return False
    total = max(0.1, float(ch.get("max", 1.0)))
    left = max(0.0, total - float(ch.get("t", 0.0)))
    used = max(0.0, min(1.0, 1.0 - left / total))
    if used > 0.004:
        veil = pg.Surface(r.size, pg.SRCALPHA)
        cx, cy, rad, a0 = r.w / 2, r.h / 2, r.w * 1.2, -math.pi / 2
        n = max(2, int(used * 48))
        pts = [(cx, cy)] + [(cx + math.cos(a0 + used * math.tau * i / n) * rad, cy + math.sin(a0 + used * math.tau * i / n) * rad) for i in range(n + 1)]
        pg.draw.polygon(veil, (8, 8, 18, 185), pts)
        scr.blit(veil, r)
    pulse = 0.55 + 0.45 * math.sin(pg.time.get_ticks() * 0.012)
    glow = tuple(min(255, int(c * pulse + 255 * (1 - pulse) * 0.35)) for c in color[:3])
    pg.draw.rect(scr, glow, r.inflate(4, 4), 3, border_radius=10)
    txt = f"{left:.1f}"
    label(scr, font, txt, r.centerx - font.size(txt)[0] // 2, r.centery - font.get_height() // 2, (255, 255, 255))
    return True


def hold_overlay(scr, pl, sid, r, font, color):
    """Индикатор заклинания-«потока» (skills.json: \"hold\": true) на иконке навыка sid в прямоугольнике r.
    Запас показан сектором: затемнена по часовой стрелке уже израсходованная часть, светлая — сколько секунд ещё осталось;
    в центре — секунды запаса. Пока поток зажат, рамка пульсирует цветом заклинания; когда клавишу отпустили, сектор
    постепенно «возвращается» (запас восстанавливается). Полный запас и нет потока — ничего не рисуем (возвращаем False)."""
    a = CFG.get("skills", {}).get(sid, {})
    if not spells.is_hold(a): return False
    total = spells.hold_max(a)
    left = spells.hold_left(pl, sid, a)
    active = spells.holding(pl, sid)
    if left >= total - 0.005 and not active: return False
    used = max(0.0, min(1.0, 1.0 - left / total))
    if used > 0.004:
        veil = pg.Surface(r.size, pg.SRCALPHA)
        cx, cy, rad, a0 = r.w / 2, r.h / 2, r.w * 1.2, -math.pi / 2
        n = max(2, int(used * 48))
        pts = [(cx, cy)] + [(cx + math.cos(a0 + used * math.tau * i / n) * rad, cy + math.sin(a0 + used * math.tau * i / n) * rad) for i in range(n + 1)]
        pg.draw.polygon(veil, (8, 8, 18, 185), pts)
        scr.blit(veil, r)
    if active:
        pulse = 0.55 + 0.45 * math.sin(pg.time.get_ticks() * 0.012)
        glow = tuple(min(255, int(c * pulse + 255 * (1 - pulse) * 0.35)) for c in color[:3])
        pg.draw.rect(scr, glow, r.inflate(4, 4), 3, border_radius=10)
    txt = f"{left:.1f}"
    label(scr, font, txt, r.centerx - font.size(txt)[0] // 2, r.centery - font.get_height() // 2, (255, 255, 255) if left > 0 else (255, 130, 130))
    return True


def spell_cell(scr, pl, sid, x, y, size, font, active=False, cost=None, per_sec=False):
    """Одна ячейка заклинания: иконка/цвет, рамка, затемнение неактивных, кулдаун и цена маны."""
    sk = CFG.get("skills", {}).get(sid, {})
    color = tuple(sk.get("color", [150, 130, 220]))
    r = pg.Rect(int(x), int(y), int(size), int(size))
    pg.draw.rect(scr, (28, 26, 42) if active else (18, 17, 28), r, border_radius=8)
    ip = spells.icon_path(sid, sk)
    img = sprite(ip, r.w - 6, r.h - 6) if ip else None
    if img: scr.blit(img, img.get_rect(center=r.center))
    else: pg.draw.circle(scr, color, r.center, max(4, size // 2 - 5))
    if not active:   # предыдущее/следующее — приглушены
        veil = pg.Surface(r.size, pg.SRCALPHA); veil.fill((8, 8, 16, 120)); scr.blit(veil, r)
    pg.draw.rect(scr, color if active else (80, 78, 105), r, 3 if active else 2, border_radius=8)
    chan = channel_overlay(scr, pl, sid, r, font, color) or hold_overlay(scr, pl, sid, r, font, color)   # удерживаемое/«поток»: индикатор вместо кулдауна
    left = max(0.0, getattr(pl, "skill_cooldowns", {}).get(sid, 0.0))
    if left > 0 and not chan:
        veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 18, 170), veil.get_rect(), border_radius=8); scr.blit(veil, r)
        label(scr, font, str(int(left + .99)), r.centerx - 4, r.centery - 8, (255, 255, 255))
    hold = spells.is_hold(sk)
    cost = float(sk.get("mana_cost", 10.0 if hold else 0)) if cost is None else cost   # cost — своя цена (арбалеты: с учётом пассивок)
    if cost:
        enough = pl.mana >= (cost * spells.HOLD_MIN_START if (hold or per_sec) else cost)
        label(scr, font, f"{cost:g}/с" if (hold or per_sec) else f"{cost:g}", r.x + 4, r.bottom - font.get_height() - 1, (140, 185, 255) if enough else (255, 120, 120))   # у потока — мана в секунду
    return r


# ---------------- вертикальные «книги»: снаряды арбалетов (Тень) и заклинания (маг) ----------------

BOOK_SMALL, BOOK_BIG, BOOK_GAP, BOOK_SPACE = 40, 56, 8, 16   # при масштабе 1: мелкая ячейка, крупная (= третье число раскладки "book"), зазор, расстояние между колонками
BOOK_HEAD = BOOK_FOOT = 14      # строка заголовка ("ЛКМ") над колонкой и подсказка клавиш под ней
BOOK_NAME = 13                  # высота строки с названием под блоком
BOOK_RATE = 16.0                # скорость плавной прокрутки при смене (больше — быстрее доезжает; ~0.2 с)
_book_anim = {}                 # ключ колонки -> состояние прокрутки {pl, n, k, off, t}


def book_kind():
    """Что показывает книга у текущего героя: "ammo" (арбалетчик), "note" (бард), "spell" (заклинатель) или None."""
    if crossbow.enabled(): return "ammo"
    if bard.enabled(): return "note"
    if CFG.get("character", {}).get("spellcaster"): return "spell"
    return None


def book_geom():
    """Геометрия блока из раскладки HUD (ключ "book": [x, y верха блока, размер крупной ячейки]); размер меняется в редакторе HUD (F2).
    Подписи (заголовок, подсказки клавиш, названия) прячутся, когда блок слишком мал (масштаб < 0.7)."""
    a = layout().get("book", [10, 150, BOOK_BIG]); big = max(16, int(a[2])); k = big / BOOK_BIG
    small, gap, space = max(10, round(BOOK_SMALL * k)), max(2, round(BOOK_GAP * k)), max(4, round(BOOK_SPACE * k))
    cols = crossbow.SIDES if book_kind() == "ammo" else 1
    labels = k >= 0.7; head = BOOK_HEAD if labels else 0; foot = BOOK_FOOT if labels else 0
    col_h = head + 2 * small + 2 * gap + big + foot
    return {"x": int(a[0]), "y": int(a[1]), "small": small, "big": big, "gap": gap, "space": space, "k": k, "cols": cols, "head": head, "foot": foot,
            "col_h": col_h, "labels": labels, "w": cols * big + (cols - 1) * space, "h": col_h + (BOOK_NAME * cols if labels else 0)}


def skill_shift():
    """На сколько слот навыка Q сдвинут от записи раскладки: у арбалетчика руки заняты арбалетами, иконок оружия нет — слот встаёт на место первого оружия
    (сразу справа от портрета); у остальных 0."""
    return -2 * (ICON + GAP) if (crossbow.enabled() or bard.enabled()) else 0


def edit_keys():
    """Какие элементы HUD показывает и двигает редактор (F2), порядок — от верхнего к нижнему при выборе мышью. У мага и арбалетчика вместо иконок оружия — книга."""
    if book_kind() in ("ammo", "note"): return ("book", "skill", "player", "mana", "hp")
    if book_kind() == "spell": return ("book", "player", "mana", "hp")
    return ("weapon2", "weapon1", "skill", "player", "mana", "hp")


def edit_rect(key, a):
    """Рамка элемента HUD в редакторе (F2): у книги — весь блок колонок с названиями, у баров — ширина x высота, у остальных — квадрат."""
    if key == "book":
        gm = book_geom(); return pg.Rect(gm["x"], gm["y"], gm["w"], gm["h"])
    r = pg.Rect(a[0], a[1], a[2], a[3] if key in ("hp", "mana") else a[2])
    if key == "skill": r.x += skill_shift()
    return r


def book_ring(pl, key):
    """(список id по кругу, индекс текущего) для колонки: "xb0"/"xb1" — снаряды арбалета 0/1, "mage" — заклинания."""
    if key.startswith("xb"):
        ids = crossbow.ammo_ids(); return ids, (pl.xb_ammo[int(key[2:])] % len(ids) if ids else 0)
    if key == "bd":
        ids = bard.note_ids(); return ids, (pl.bd_note % len(ids) if ids else 0)
    act = spells.active_skills(pl); return act, (pl.skill_index % len(act) if act else 0)


def book_scroll(pl, key, n, k):
    """Плавная прокрутка колонки. Возвращает смещение off в ячейках: после смены на d шагов ячейки стартуют со сдвигом d и «доезжают» до 0
    (ease-out, не зависит от FPS). Частые нажатия складываются, список не прыгает. Новый игрок/другая длина списка — без анимации."""
    now = pg.time.get_ticks(); st = _book_anim.get(key)
    if st is None or st["pl"] != id(pl) or st["n"] != n:
        st = _book_anim[key] = {"pl": id(pl), "n": n, "k": k, "off": 0.0, "t": now}
    if k != st["k"]:
        d = k - st["k"]
        if n > 1 and abs(d) * 2 > n: d -= n if d > 0 else -n   # короткий путь по кругу (из последнего в первый — на шаг вперёд)
        st["off"] = max(-2.0, min(2.0, st["off"] + d)); st["k"] = k
    dt = min(0.1, max(0.0, (now - st["t"]) / 1000.0)); st["t"] = now
    st["off"] -= st["off"] * (1 - math.exp(-dt * BOOK_RATE))
    if abs(st["off"]) < 0.004: st["off"] = 0.0
    return st["off"]


def label_a(scr, font, text, x, y, col, alpha=1.0):
    """label() с прозрачностью (alpha 0..1) — для названий, которые проявляются после смены."""
    a = int(255 * max(0.0, min(1.0, alpha)))
    for dx, dy, c in ((1, 1, (0, 0, 0)), (0, 0, col)):
        s = font.render(text, True, c); s.set_alpha(a); scr.blit(s, (x + dx, y + dy))


def book_cell(scr, pl, font, sid, cx, cy, size, alpha, active, cost=None, extra=None, per_sec=False):
    """Ячейка по центру (cx, cy) заданного размера и прозрачности: рисуется во временную поверхность (с полями под рамку-вспышку), чтобы прозрачность
    действовала на всё сразу. extra(поверхность, rect) дорисовывает поверх (перезарядка арбалета, вспышка смены, точка гарпуна)."""
    size = max(8, int(round(size / 2.0)) * 2); pad = 6   # чётные размеры — меньше разных вариантов картинок в кэше при анимации
    tmp = pg.Surface((size + 2 * pad, size + 2 * pad), pg.SRCALPHA)
    spell_cell(tmp, pl, sid, pad, pad, size, font, active=active, cost=cost, per_sec=per_sec)
    if extra: extra(tmp, pg.Rect(pad, pad, size, size), sid)
    if alpha < 1: tmp.set_alpha(int(255 * max(0.0, alpha)))
    scr.blit(tmp, (int(cx - tmp.get_width() / 2), int(cy - tmp.get_height() / 2)))


def ammo_extra(pl, i):
    """Дорисовка поверх текущего снаряда арбалета i: сектор перезарядки, вспышка рамки при смене, точка состояния гарпуна."""
    def f(tmp, rc, sid):
        color = tuple(CFG.get("skills", {}).get(sid, {}).get("color", [150, 130, 220]))
        cd = max(0.0, pl.xb_cd[i])
        if cd > 0:   # перезарядка: затемнение сверху вниз сжимается по мере готовности (цифр нет — паузы короткие)
            veil = pg.Surface(rc.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 18, 175), (0, 0, rc.w, max(1, round(rc.h * min(1.0, cd / crossbow.cooldown_total(pl, i))))), border_radius=8)
            tmp.blit(veil, rc)
        if pl.xb_notice[i] > 0: book_flash(tmp, rc, color, pl.xb_notice[i] / 0.5)
        h = pl.hooks[i]
        if h:   # гарпун в деле: жёлтая точка — летит, зелёная — зацепился (арбалет занят, пока гарпун не отцеплен)
            pg.draw.circle(tmp, (100, 240, 150) if h["st"] == "hold" else (255, 220, 90), (rc.right - max(4, rc.w // 8), rc.y + max(4, rc.w // 8)), max(3, rc.w // 14))
    return f


def spell_extra(pl):
    """Дорисовка поверх текущего заклинания мага: вспышка рамки при смене."""
    def f(tmp, rc, sid):
        if getattr(pl, "skill_notice", 0) > 0: book_flash(tmp, rc, tuple(CFG.get("skills", {}).get(sid, {}).get("color", [150, 130, 220])), pl.skill_notice / 0.5)
    return f


def note_extra(pl):
    """Дорисовка поверх выбранной ноты барда: вспышка рамки при смене и пульсирующее кольцо, пока нота играет."""
    def f(tmp, rc, sid):
        color = tuple(CFG.get("skills", {}).get(sid, {}).get("color", [150, 130, 220]))
        if pl.bd_notice > 0: book_flash(tmp, rc, color, pl.bd_notice / 0.5)
        if pl.bd_play:
            k = 0.5 + 0.5 * math.sin(pg.time.get_ticks() / 1000.0 * 9.0)
            pg.draw.rect(tmp, tuple(min(255, int(c + (255 - c) * k * 0.6)) for c in color), rc.inflate(4 + int(3 * k), 4 + int(3 * k)), 2, border_radius=10)
    return f


def book_flash(tmp, rc, color, f):
    """Рамка вокруг ячейки, вспыхивающая цветом навыка и гаснущая (f: 1 → 0)."""
    f = max(0.0, min(1.0, f)); glow = tuple(min(255, int(c + (255 - c) * f)) for c in color)
    pg.draw.rect(tmp, glow, rc.inflate(6, 6), 2, border_radius=10)


def book_column(scr, pl, font, key, x, gm, title, hint, cost_fn, extra, per_sec=False):
    """Колонка из ячеек: мелкая (предыдущий) сверху · крупная (текущий) · мелкая (следующий) снизу, над ней заголовок, под ней подсказка клавиш.
    Каждая ячейка стоит на «дорожке» с дробным номером r+off (off — прокрутка): размер, положение и прозрачность плавно меняются между якорями
    (текущий → мелкий сосед → исчезающий), поэтому при смене список скользит, а новая крупная ячейка вырастает из мелкой.
    Возвращает (id текущего, off) — для строки с названием."""
    ids, k = book_ring(pl, key)
    if not ids: return None
    n = len(ids); off = book_scroll(pl, key, n, k)
    small, big, gap = gm["small"], gm["big"], gm["gap"]
    cx = x + big / 2; c0 = gm["y"] + gm["head"] + small + gap + big / 2     # центр крупной ячейки
    c1 = big / 2 + gap + small / 2; c2 = c1 + small + gap                  # расстояние от центра до якорей соседа и «исчезающего»
    def center(r): a = abs(r); d = a * c1 if a <= 1 else c1 + (min(a, 2) - 1) * (c2 - c1); return c0 + (d if r >= 0 else -d)
    def size_of(a): return small + (big - small) * (1 - a) if a <= 1 else small * (1 - 0.35 * (a - 1))
    items = []
    for r in range(-4, 5):
        if n == 1 and r != 0: continue
        if n == 2 and r == -1 and abs(off) < 0.01: continue   # два заклинания: предыдущий и следующий — один и тот же, покой — без дубля
        a = abs(r + off)
        if a < 2: items.append((a, r))
    prev_clip = scr.get_clip()   # прокрутка обрезана областью колонки: уходящие ячейки скользят «под» заголовок и подсказку клавиш, а не наезжают на текст
    scr.set_clip(pg.Rect(int(x) - 6, gm["y"] + gm["head"], big + 12, 2 * small + 2 * gap + big))
    for a, r in sorted(items, reverse=True):   # дальние рисуем первыми, текущий — сверху всех
        sid = ids[(k + r) % n]
        book_cell(scr, pl, font, sid, cx, center(r + off), size_of(a), 1.0 if a <= 1 else 1.0 - (a - 1), a < 0.5,
                  cost=cost_fn(sid) if cost_fn else None, extra=extra if r == 0 else None, per_sec=per_sec)
    scr.set_clip(prev_clip)
    if gm["labels"]:
        tw = font.size(title)[0]; label(scr, font, title, int(cx - tw / 2), gm["y"], (255, 230, 150))
        if n > 1:
            hw = font.size(hint)[0]; label(scr, font, hint, int(cx - hw / 2), gm["y"] + gm["head"] + 2 * small + 2 * gap + big + 1, (170, 170, 195))
    return ids[k], off


def book_draw(scr, pl, font):
    """Рисует книгу текущего героя (см. book_kind): колонки слева направо — ЛКМ-арбалет, ПКМ-арбалет (или одна колонка заклинаний мага), под ними названия."""
    kind = book_kind()
    if kind is None: return
    gm = book_geom(); defs = CFG.get("skills", {}); ctl = SETTINGS.get("controls", {}); names = []
    if kind == "ammo":
        for i in range(gm["cols"]):
            n = i + 1; hint = f"{str(ctl.get(f'ammo{n}_prev', str(2 * n - 1))).upper()}/{str(ctl.get(f'ammo{n}_next', str(2 * n))).upper()}"
            r = book_column(scr, pl, font, f"xb{i}", gm["x"] + i * (gm["big"] + gm["space"]), gm, "ЛКМ" if i == 0 else "ПКМ", hint,
                            lambda sid: crossbow.mana_cost(pl, sid), ammo_extra(pl, i))
            if r: names.append((("ЛКМ: " if i == 0 else "ПКМ: ") + defs.get(r[0], {}).get("name", r[0]), tuple(defs.get(r[0], {}).get("color", [235, 225, 255])), r[1]))
    elif kind == "note":
        hint = f"{str(ctl.get('ammo1_prev', '1')).upper()}/{str(ctl.get('ammo1_next', '2')).upper()}"
        r = book_column(scr, pl, font, "bd", gm["x"], gm, "Ноты", hint, lambda sid: float(defs.get(sid, {}).get("mana_cost", 0)), note_extra(pl), per_sec=True)
        if r: names.append((defs.get(r[0], {}).get("name", r[0]), tuple(defs.get(r[0], {}).get("color", [235, 225, 255])), r[1]))
    else:
        hint = f"{str(ctl.get('skill_prev', 'V')).upper()}/{str(ctl.get('skill_next', 'C')).upper()}"
        r = book_column(scr, pl, font, "mage", gm["x"], gm, "Заклинания", hint, None, spell_extra(pl))
        if r: names.append((defs.get(r[0], {}).get("name", r[0]), tuple(defs.get(r[0], {}).get("color", [235, 225, 255])), r[1]))
    if gm["labels"]:   # названия выбранного под блоком; после смены чуть проявляются заново
        for j, (text, col, off) in enumerate(names):
            light = tuple(min(255, int(c + (255 - c) * 0.45)) for c in col)
            label_a(scr, font, text, gm["x"], gm["y"] + gm["col_h"] + 2 + j * BOOK_NAME, light, 1.0 - 0.6 * min(1.0, abs(off)))


def skill_slot(scr, pl, font, pos=None):
    """Слот активного навыка (Q): иконка, название, кулдаун/индикатор потока. pos — [x, y, размер] вместо положения из раскладки."""
    defs = CFG.get("skills", {})
    active_skills = [sid for sid in getattr(pl, "skills", []) if defs.get(sid, {}).get("category", "active") == "active"]
    if active_skills:
        pl.skill_index %= len(active_skills)
        sid = active_skills[pl.skill_index]
        skill = defs.get(sid, {"name": sid, "color": [150, 130, 220], "cooldown": 1})
        r = slot(scr, 3, spells.icon_path(sid, skill), lambda r: pg.draw.circle(scr, skill.get("color", [150, 130, 220]), r.center, 13), border=tuple(skill.get("color", [150, 130, 220])), layout_key="skill", pos=pos)
        label(scr, font, "Q", r.x + 4, r.y + 3, (255, 230, 150))
        scol = tuple(skill.get("color", [150, 130, 220]))
        chan = channel_overlay(scr, pl, sid, r, font, scol) or hold_overlay(scr, pl, sid, r, font, scol)   # удерживаемое/«поток»: индикатор запаса
        left = max(0.0, getattr(pl, "skill_cooldowns", {}).get(sid, 0.0))
        if chan: pass
        elif left > 0:
            veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 18, 165), veil.get_rect(), border_radius=8); scr.blit(veil, r)
            label(scr, font, str(int(left + .99)), r.centerx - 4, r.centery - 8, (255, 255, 255))
        else:
            pg.draw.circle(scr, (100, 240, 150), (r.right - 7, r.bottom - 7), 4)
        nm = font.render(skill.get("name", sid), True, (225, 220, 245))
        scr.blit(nm, (r.x + (r.w - nm.get_width()) // 2, r.y - nm.get_height() - 2))


def icons(scr, pl, font):
    portrait(scr, pl, font)

    # Сначала оружие (ЛКМ, ПКМ), затем активный навык Q. Пассивные навыки
    # не отображаются в панели и не участвуют в переключении заклинаний.
    weapon_slots(scr, pl, font)
    skill_slot(scr, pl, font)   # активный навык рисуется последним, справа от двух оружий


def weapon_slots(scr, pl, font):
    """Оружие в руках (ЛКМ, ПКМ). Занятые способностью героя руки не рисуются. Пустая рука: у обычного героя — пустая ячейка
    (оружие убрано в рюкзак), у мага/барда/Тени — ничего (у них оружие необязательно)."""
    Wp = CFG["weapons"]; opened = inventory.open_hands(pl); classic = inventory.uses_weapons(pl)
    for n, (key, wid) in enumerate(zip(("ЛКМ", "ПКМ"), pl.slots[:2])):
        if not opened[n]: continue
        if wid not in Wp:   # рука пуста (оружие убрано в рюкзак) — пустая ячейка с подписью
            if not classic: continue
            r = slot(scr, n + 1, None, lambda r: None, layout_key="weapon1" if n == 0 else "weapon2"); label(scr, font, key, r.x + 4, r.y + 3, (255, 230, 150)); continue
        w = Wp[wid]; r = slot(scr, n + 1, w.get("icon", f"icons/{wid}.png"), lambda r, wid=wid: weapon.icon(scr, wid, r.centerx, r.centery, int(r.w * .75)), layout_key="weapon1" if n == 0 else "weapon2")
        cost = weapon.mana_cost(wid, w["combo"][0])
        if pl.mana < cost:   # не хватает маны — иконка темнеет
            veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (10, 10, 20, 130), veil.get_rect(), border_radius=8); scr.blit(veil, r)
        label(scr, font, key, r.x + 4, r.y + 3, (255, 230, 150))
        t = font.render(str(cost), True, (140, 185, 255)); label(scr, font, str(cost), r.right - t.get_width() - 4, r.bottom - t.get_height() - 2, (140, 185, 255))


def draw_boss_bar(scr, mobs, font):
    """Большая настраиваемая полоса здоровья активного босса в верхней части экрана."""
    boss = next((m for m in mobs if m.d.get("boss") and m.hp > 0), None)
    if boss is None: return
    cfg = CFG.get("boss", {}).get("bar", {})
    x = int(cfg.get("x", (W - cfg.get("w", 620)) / 2))
    y = int(cfg.get("y", 34)); w = int(cfg.get("w", 620)); h = int(cfg.get("h", 22))
    ratio = max(0.0, min(1.0, boss.hp / max(1, boss.maxhp)))
    back = sprite(cfg.get("back_skin"), w, h) if cfg.get("back_skin") else None
    fill = sprite(cfg.get("fill_skin"), w, h) if cfg.get("fill_skin") else None
    frame = sprite(cfg.get("frame_skin"), w, h) if cfg.get("frame_skin") else None
    if back: scr.blit(back, (x, y))
    else: pg.draw.rect(scr, tuple(cfg.get("back", [35, 18, 25])), (x, y, w, h), border_radius=int(cfg.get("radius", 6)))
    fw = int(w * ratio)
    if fw:
        if fill:
            scr.blit(fill, (x, y), pg.Rect(0, 0, fw, h))
        else:
            pg.draw.rect(scr, tuple(cfg.get("fill", [190, 38, 55])), (x, y, fw, h), border_radius=int(cfg.get("radius", 6)))
    if frame: scr.blit(frame, (x, y))
    else: pg.draw.rect(scr, tuple(cfg.get("border", [235, 190, 150])), (x, y, w, h), max(1, int(cfg.get("border_width", 2))), border_radius=int(cfg.get("radius", 6)))
    title = str(CFG.get("boss", {}).get("name", boss.d.get("name", "БОСС")))
    title_font = pg.font.SysFont("arial,dejavusans,freesans", int(cfg.get("font_size", 18)), bold=True)
    label = title_font.render(title, True, tuple(cfg.get("text", [255, 235, 220])))
    scr.blit(label, label.get_rect(center=(x + w // 2, y - int(cfg.get("title_gap", 12)) - label.get_height() // 2)))
    if cfg.get("show_numbers", True):
        nums = font.render(f"{max(0, int(boss.hp))} / {int(boss.maxhp)}", True, tuple(cfg.get("number_color", [255, 255, 255])))
        scr.blit(nums, nums.get_rect(center=(x + w // 2, y + h // 2)))
    # Моргарт: пока живы руки, голова под щитом; под её полосой — общая полоса здоровья рук.
    hands = getattr(boss, "hands", None)
    if hands is not None and hands.list:
        left = hands.alive_count()
        if left and boss.head_shielded():
            shade = pg.Surface((w, h), pg.SRCALPHA); shade.fill((90, 90, 110, 150)); scr.blit(shade, (x, y))
        if left:
            hy = y + h + 6; hh = max(8, h // 2)
            pg.draw.rect(scr, tuple(cfg.get("back", [35, 18, 25])), (x, hy, w, hh), border_radius=4)
            pg.draw.rect(scr, (255, 170, 60), (x, hy, int(w * hands.hp_ratio()), hh), border_radius=4)
            pg.draw.rect(scr, tuple(cfg.get("border", [235, 190, 150])), (x, hy, w, hh), 1, border_radius=4)
            txt = font.render(f"РУКИ {left}/{len(hands.list)}" + ("  —  голова под щитом" if boss.head_shielded() else ""), True, (255, 235, 200))
            scr.blit(txt, txt.get_rect(center=(x + w // 2, hy + hh // 2)))
