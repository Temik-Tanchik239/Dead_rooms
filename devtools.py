"""Инструменты разработчика: меню на F6 и тренировочный манекен.

Меню (DevMenu) — только в одиночной игре. Игра на паузе, пока оно открыто. Что умеет:
  · выдать опыт / здоровье / ману (число в поле + «Выдать»; для здоровья и маны можно отрицательное число —
    здоровье при этом не опустится ниже 1, чтобы не убить героя);
  · заспавнить тренировочного манекена рядом с героем, убрать всех манекенов, сбросить его счётчики и эффекты.

Манекен (Dummy) — обычный Mob (лежит в r.mobs, поэтому по нему попадают атаки, пули и заклинания), но:
  · стоит на месте, не атакует; урон не отбрасывает и не сбивает его (а вот телекинез/толчки заклинаний двигают);
  · не умирает: здоровье не убывает ни от ударов, ни от горения, ни от пуль (см. свойство hp);
  · над ним показываются последний удар, суммарный урон, DPS за 5 с и активные эффекты (стан/заморозка/горение);
  · стан, заморозка, горение и прочие эффекты из status.py действуют на него как на обычного моба
    (иммунитета к контролю нет — как раз чтобы тестировать эффекты).
Манекен не лежит в data/mobs.json: его описание DEF подставляется в CFG["mobs"] только на момент создания, чтобы
генератор комнат (maps.py) не выбрал его случайным мобом. Сетевая игра манекенов не поддерживает (меню там закрыто).

Внешность — через ассеты (как у босса в assets/boss/): папка assets/dummy/. Всё необязательно, без файлов рисуется
соломенное чучело по умолчанию:
  dummy.json        — настройки: name; w, h (хитбокс, действует на новых манекенах); draw [ширина, высота] и offset [dx, dy]
                      спрайта (по умолчанию = хитбокс и 0); skin (путь к скину внутри assets, по умолчанию dummy/dummy.png);
                      hurt_time (сколько секунд играть «удар», 0.25); anims и anim_fps — как у мобов (см. anim.py);
  dummy.png         — одиночный скин (используется, если нет анимации нужного состояния);
  idle/ hurt/ stun/ frozen/ burn/  — папки кадров 1.png, 2.png, ... для состояний: покой, только что ударили, оглушён,
                      заморожен, горит. Нет кадров состояния — берётся idle, потом скин, потом чучело по умолчанию.
F5 перечитывает файлы и обновляет уже стоящие манекены (кроме хитбокса).
"""
import copy, math
import pygame as pg
from core import CFG, W, VIEW_H, T, free
from mob import Mob
from anim import sprite, mob_frame, ASSETS_EXISTS
import status

KIND = "__dummy__"
DEF = {"name": "Тренировочный манекен", "w": 34, "h": 60, "hp": 1_000_000, "xp": 0, "dummy": True,
       "move": {"type": "stand"}, "attacks": [], "color": [214, 184, 118],
       "skin": "dummy/dummy.png", "hurt_time": 0.25}
ASSET_DIR = "dummy"          # папка кадров состояний: assets/dummy/<состояние>/
LOCKED = ("hp", "xp", "move", "attacks", "dummy")   # эти поля dummy.json менять нельзя — манекен перестанет быть манекеном


def look():
    """Описание манекена: DEF + то, что лежит в assets/dummy/dummy.json (CFG["dummy"], перечитывается по F5)."""
    d = copy.deepcopy(DEF); cfg = CFG.get("dummy")
    if isinstance(cfg, dict): d.update({k: v for k, v in cfg.items() if k not in LOCKED})
    return d
DPS_WINDOW = 5.0   # за сколько последних секунд считается DPS
_font = None


def _f():
    """Шрифт подписей над манекеном (создаётся при первой отрисовке, когда pygame уже инициализирован)."""
    global _font
    if _font is None: _font = pg.font.SysFont("arial,dejavusans,freesans", 14, bold=True)
    return _font


def hostile(mobs):
    """Мобы без манекенов: именно они держат двери закрытыми и не дают «зачистить» комнату."""
    return [m for m in mobs if not getattr(m, "is_dummy", False)]


def _fmt(n):
    return f"{n:,.0f}".replace(",", " ")


class Dummy(Mob):
    is_dummy = True

    def __init__(s, x, y):
        s._hp = None; s.total = 0.0; s.last_hit = 0.0; s.log = []; s._dot = s._dot_t = 0.0; s.hurt_left = 0.0
        CFG["mobs"][KIND] = look()                       # Mob.__init__ читает описание из CFG; сразу убираем обратно
        try: super().__init__(KIND, x, y, 1.0)
        finally: CFG["mobs"].pop(KIND, None)
        s.home = (s.x, s.y)

    # ---------- неубиваемость и учёт урона ----------
    @property
    def hp(s): return s._hp

    @hp.setter
    def hp(s, v):
        """Любое уменьшение здоровья (удар, горение, пуля — все пишут в m.hp) попадает в счётчики, а само здоровье не меняется."""
        old = s._hp
        if old is not None and v < old:
            s.total += old - v; s.log.append((getattr(s, "t", 0.0), old - v))
            return
        s._hp = v

    def hurt(s, dmg, kb, fx):
        """Удар: считаем урон, показываем число; без отбрасывания, стана и сбития атак."""
        s.last_hit = dmg; s.hp -= dmg; s.flash = .1; fx.stop = .05
        s.hurt_left = float(look().get("hurt_time", .25)); s.anim = ""   # анимация «удар» стартует заново
        fx.text(str(int(dmg)), s.cx, s.y)

    def dps(s):
        s.log = [(t, d) for t, d in s.log if s.t - t <= DPS_WINDOW]
        if not s.log: return 0.0
        return sum(d for _, d in s.log) / max(1.0, min(DPS_WINDOW, s.t - s.log[0][0]))

    def reset(s):
        """Обнулить счётчики урона и снять все эффекты."""
        s.total = s.last_hit = 0.0; s.log = []; s._dot = s._dot_t = 0.0
        s.stun = s.frozen = s.burn = s.burn_dps = 0.0

    # ---------- жизнь ----------
    def update(s, dt, w):
        before = s.total; s.hurt_left -= dt
        super().update(dt, w)
        dot = s.total - before                     # за собственный update урон идёт только от горения
        if dot > 0:
            s._dot += dot; s._dot_t += dt
            if s._dot_t >= .5:
                w.fx.text(f"{int(round(s._dot))} ожог", s.cx, s.y - 8); s._dot = s._dot_t = 0.0
        if s.y > len(w.g) * T + 100 or s.y < -300 or s.x < -300 or s.x > len(w.g[0]) * T + 300:   # улетел за карту — на место
            s.x, s.y = s.home; s.vx = s.vy = 0.0

    def anim_states(s):
        """Состояние для анимации из ассетов (Mob.update_anim ведёт таймер): по приоритету; нет кадров — следующее, в конце idle."""
        if s.frozen > 0: return ["frozen", "stun", "idle"], None
        if s.stun > 0: return ["stun", "idle"], None
        if s.hurt_left > 0: return ["hurt", "idle"], None
        if s.burn > 0: return ["burn", "idle"], None
        return ["idle"], None

    def _box(s, d):
        """Где рисовать спрайт: (ширина, высота, x, y). По умолчанию размер = хитбокс, низ = низ хитбокса; offset сдвигает."""
        r = s.rect; dw, dh = d.get("draw", [r.w, r.h]); ox, oy = d.get("offset", [0, 0])
        return int(dw), int(dh), r.centerx - int(dw) // 2 + int(ox), r.bottom - int(dh) + int(oy)

    def draw(s, v, debug=False):
        d = look(); r = s.rect; hot = s.flash > 0
        path = mob_frame(KIND, d, s.anim.split("|"), s.anim_t, None, folder=ASSET_DIR)
        img = None
        if ASSETS_EXISTS(path):                       # нет файла — молча рисуем чучело по умолчанию (без предупреждений)
            dw, dh, x, y = s._box(d); img = sprite(path, dw, dh, False, hot)
        if img:
            v.blit(img, (x, y))
            tcol = status.tint(s)                     # заморожен — синий, горит — оранжевый: красим только силуэт спрайта
            if tcol: v.blit(pg.mask.from_surface(img).to_surface(setcolor=tcol, unsetcolor=(0, 0, 0, 0)), (x, y))
            top = y
        else:
            s._draw_default(v, r, hot); top = r.top
            tcol = status.tint(s)
            if tcol:
                glow = pg.Surface((r.w + 40, r.h), pg.SRCALPHA); ox = 20
                pg.draw.rect(glow, tcol, (ox + 4, 16, 26, 28), border_radius=6); pg.draw.circle(glow, tcol, (ox + 17, 8), 8)
                v.blit(glow, (r.x - ox, r.top))
        if s.stun > 0:                                                                 # звёздочки над головой
            for k in range(3):
                a = s.t * 6 + k * 2.09
                pg.draw.circle(v, (255, 230, 90), (int(r.centerx + math.cos(a) * 13), int(top - 6 + math.sin(a) * 4)), 3)
        if debug: pg.draw.rect(v, (0, 255, 0), r, 1)

    @staticmethod
    def _draw_default(v, r, hot=False):
        """Соломенное чучело с мишенью на груди — рисуется, когда в assets/dummy нет подходящей картинки. Умещается в r (34x60)."""
        cx, top, bot = r.centerx, r.top, r.bottom
        straw, wood, dark = (255, 255, 255) if hot else (214, 184, 118), (104, 76, 48), (60, 44, 30)
        pg.draw.rect(v, dark, (cx - 15, bot - 5, 30, 5), border_radius=2)             # основание
        pg.draw.rect(v, wood, (cx - 2, top + 20, 4, r.h - 24))                         # стойка
        pg.draw.line(v, wood, (cx - 17, top + 20), (cx + 17, top + 20), 3)             # «руки»
        torso = pg.Rect(cx - 13, top + 16, 26, 28)
        pg.draw.rect(v, straw, torso, border_radius=6); pg.draw.rect(v, dark, torso, 2, border_radius=6)
        pg.draw.circle(v, straw, (cx, top + 8), 8); pg.draw.circle(v, dark, (cx, top + 8), 8, 2)
        for rad, col in ((10, (190, 50, 50)), (6, (240, 240, 240)), (3, (190, 50, 50))):
            pg.draw.circle(v, col, torso.center, rad)                                  # мишень на груди

    def draw_overlay(s, scr, cam, zoom):
        """Табличка над манекеном — поверх готового кадра (после освещения, в экранных координатах): так она яркая и чёткая
        даже на тёмных картах. Зовётся из Game.draw после lighting.apply."""
        r = s.rect; top = min(r.top, s._box(look())[3])      # над самой высокой точкой: хитбокса или спрайта
        s._draw_panel(scr, int((r.centerx - cam[0]) * zoom), int((top - cam[1]) * zoom) - 6)

    def _draw_panel(s, v, cx, bottom):
        """Табличка над манекеном: последний удар, всего, DPS и активные эффекты."""
        lines = [(f"Удар: {_fmt(s.last_hit)}    Всего: {_fmt(s.total)}", (255, 255, 255)), (f"DPS ({DPS_WINDOW:g} с): {_fmt(s.dps())}", (255, 220, 130))]
        if s.frozen > 0: lines.append((f"Заморожен {s.frozen:.1f} с", (150, 215, 255)))
        elif s.stun > 0: lines.append((f"Оглушён {s.stun:.1f} с", (255, 230, 90)))
        if s.burn > 0: lines.append((f"Горит {s.burn:.1f} с ({s.burn_dps:g}/с)", (255, 150, 70)))
        font = _f(); imgs = [(font.render(t, True, c), font.render(t, True, (0, 0, 0))) for t, c in lines]   # (текст, тень)
        pw, ph = max(i.get_width() for i, _ in imgs) + 14, sum(i.get_height() for i, _ in imgs) + 8
        x, y = max(2, min(v.get_width() - pw - 2, int(cx - pw / 2))), max(2, int(bottom - ph))
        bg = pg.Surface((pw, ph), pg.SRCALPHA); pg.draw.rect(bg, (8, 8, 18, 220), bg.get_rect(), border_radius=5)
        v.blit(bg, (x, y)); yy = y + 4
        for i, sh in imgs:
            v.blit(sh, (x + 8, yy + 1)); v.blit(i, (x + 7, yy)); yy += i.get_height()


class DevMenu:
    """Окно разработчика (F6). Рисуется поверх игры на логическом экране; сама игра ставится на паузу (см. Game.step)."""
    PW, PH = 560, 352
    ROWS = (("xp", "Опыт"), ("hp", "Здоровье"), ("mana", "Мана"))

    def __init__(s, game):
        s.g = game; s.open = False; s.msg = ""
        s.values = {"xp": "100", "hp": "50", "mana": "50"}; s.focus = "xp"

    # ---------- открытие ----------
    def available(s):
        g = s.g
        return g.net is None and g.menu_mode is None and not (g.show_world or g.level_menu or g.controls_open or g.hud_edit)

    def toggle(s):
        if s.open: s.open = False; return
        g = s.g
        if g.net is not None: g.fx.text("Меню разработчика недоступно в сетевой игре", g.pl.cx, g.pl.y - 30); return
        if s.available(): s.open = True; s.msg = ""

    # ---------- действия ----------
    def _amount(s, kind):
        try: return int(s.values[kind])
        except ValueError: return None

    def apply(s, kind, full=False):
        g, pl = s.g, s.g.pl
        amt = s._amount(kind)
        if amt is None and not full: s.msg = "Введите целое число"; return
        if kind == "xp":
            if full: amt = max(0, pl.xp_next - pl.xp)      # «До уровня»: ровно столько, сколько не хватает
            if amt <= 0: s.msg = "Опыт можно только выдать (число больше 0)"; return
            g.gain_xp(amt); s.msg = f"Выдано {_fmt(amt)} опыта"
            if g.level_menu: s.open = False                # повысился уровень: пусть игрок увидит окно выбора навыка
        elif kind == "hp":
            pl.hp = pl.maxhp if full else max(1, min(pl.maxhp, pl.hp + amt)); s.msg = f"Здоровье: {pl.hp:.0f} / {pl.maxhp:.0f}"
        elif kind == "mana":
            pl.mana = pl.maxmana if full else max(0, min(pl.maxmana, pl.mana + amt)); s.msg = f"Мана: {pl.mana:.0f} / {pl.maxmana:.0f}"

    def spawn_dummy(s):
        """Поставить манекена на землю рядом с героем (сначала со стороны, куда он смотрит)."""
        g, pl, r = s.g, s.g.pl, s.g.room
        w, h = DEF["w"], DEF["h"]; face = pl.face or 1
        for off in (120, -120, 170, -170, 80, -80, 220, -220):
            rect = pg.Rect(int(pl.cx + off * face - w / 2), int(pl.y + pl.h - h), w, h)
            if free(r.g, rect) and not free(r.g, rect.move(0, 4)):      # место свободно и под ногами есть опора
                r.mobs.append(Dummy(rect.x, rect.y)); s.msg = "Манекен заспавнен"; return
        s.msg = "Нет свободного места рядом с героем"

    def dummies(s): return [m for m in s.g.room.mobs if getattr(m, "is_dummy", False)]

    def remove_dummies(s):
        n = len(s.dummies()); s.g.room.mobs = hostile(s.g.room.mobs)
        s.msg = f"Убрано манекенов: {n}" if n else "Манекенов нет"

    def reset_dummies(s):
        for d in s.dummies(): d.reset()
        s.msg = "Счётчики и эффекты манекенов сброшены" if s.dummies() else "Манекенов нет"

    # ---------- раскладка ----------
    def layout(s):
        """Прямоугольники всех элементов: {"panel", "fields": {kind: Rect}, "buttons": [(id, Rect, label)]}."""
        px, py = W // 2 - s.PW // 2, max(8, VIEW_H // 2 - s.PH // 2)
        L = {"panel": pg.Rect(px, py, s.PW, s.PH), "fields": {}, "buttons": []}
        for i, (kind, _) in enumerate(s.ROWS):
            y = py + 78 + i * 44
            L["fields"][kind] = pg.Rect(px + 130, y, 130, 32)
            L["buttons"].append((("give", kind), pg.Rect(px + 272, y, 110, 32), "Выдать"))
            L["buttons"].append((("full", kind), pg.Rect(px + 388, y, 152, 32), {"xp": "До след. уровня", "hp": "Полное", "mana": "Полная"}[kind]))
        by = py + 250
        for i, (act, label) in enumerate((("spawn", "Спавн манекена"), ("remove", "Убрать манекены"), ("reset", "Сбросить счётчик"))):
            L["buttons"].append(((act, None), pg.Rect(px + 20 + i * 172, by, 166, 34), label))
        return L

    def click(s, pos):
        L = s.layout()
        for kind, rect in L["fields"].items():
            if rect.collidepoint(pos): s.focus = kind; return
        for (act, kind), rect, _ in L["buttons"]:
            if rect.collidepoint(pos):
                if act == "give": s.focus = kind; s.apply(kind)
                elif act == "full": s.focus = kind; s.apply(kind, full=True)
                elif act == "spawn": s.spawn_dummy()
                elif act == "remove": s.remove_dummies()
                elif act == "reset": s.reset_dummies()
                return

    # ---------- события (True — событие поглощено, игре не передавать) ----------
    def event(s, e):
        if not s.open: return False
        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1: s.click(e.pos)
        elif e.type == pg.KEYDOWN:
            kinds = [k for k, _ in s.ROWS]; f = s.focus
            if e.key in (pg.K_F6, pg.K_ESCAPE): s.open = False
            elif e.key == pg.K_TAB: s.focus = kinds[(kinds.index(f) + (-1 if e.mod & pg.KMOD_SHIFT else 1)) % len(kinds)]
            elif e.key in (pg.K_RETURN, pg.K_KP_ENTER): s.apply(f)
            elif e.key == pg.K_BACKSPACE: s.values[f] = s.values[f][:-1]
            elif e.unicode and e.unicode in "0123456789" and len(s.values[f].lstrip("-")) < 9: s.values[f] += e.unicode
            elif e.unicode == "-" and f != "xp" and not s.values[f]: s.values[f] = "-"
        return True

    # ---------- отрисовка ----------
    def draw(s, scr):
        g = s.g; L = s.layout(); p = L["panel"]; pl = g.pl; mouse = pg.mouse.get_pos()
        scr.blit(g.veil, (0, 0))
        pg.draw.rect(scr, (30, 28, 46), p, border_radius=10); pg.draw.rect(scr, (130, 120, 165), p, 2, border_radius=10)
        g.txt("МЕНЮ РАЗРАБОТЧИКА", p.x + 20, p.y + 14, (240, 235, 255), g.font)
        g.txt("F6 / Esc — закрыть (игра на паузе)", p.right - 235, p.y + 17, (170, 170, 200), g.small)
        g.txt(f"Ур. {pl.level}   Опыт {pl.xp}/{pl.xp_next}   HP {pl.hp:.0f}/{pl.maxhp:.0f}   Мана {pl.mana:.0f}/{pl.maxmana:.0f}", p.x + 20, p.y + 46, (255, 220, 130), g.small)
        for kind, label in s.ROWS:
            rect = L["fields"][kind]
            g.txt(label, p.x + 20, rect.y + 8, (235, 235, 245), g.font)
            pg.draw.rect(scr, (20, 18, 32), rect, border_radius=5)
            pg.draw.rect(scr, (255, 220, 130) if s.focus == kind else (110, 100, 140), rect, 2, border_radius=5)
            caret = "|" if s.focus == kind and pg.time.get_ticks() // 450 % 2 == 0 else ""
            g.txt(s.values[kind] + caret, rect.x + 10, rect.y + 8, (255, 255, 255), g.font)
        for _, rect, label in L["buttons"]:
            hover = rect.collidepoint(mouse)
            pg.draw.rect(scr, (105, 75, 130) if hover else (58, 52, 78), rect, border_radius=5)
            pg.draw.rect(scr, (170, 150, 205) if hover else (130, 120, 165), rect, 1, border_radius=5)
            img = g.font.render(label, True, (235, 235, 245)); scr.blit(img, img.get_rect(center=rect.center))
        pg.draw.line(scr, (90, 84, 120), (p.x + 20, p.y + 232), (p.right - 20, p.y + 232), 1)
        g.txt("Манекен: стоит, не умирает, показывает урон и DPS, принимает эффекты", p.x + 20, p.y + 236, (190, 190, 215), g.small)
        n = len(s.dummies())
        g.txt(f"Манекенов в комнате: {n}", p.x + 20, p.y + 296, (190, 190, 215), g.small)
        g.txt("Enter — применить поле · Tab — следующее поле · для HP/маны можно число со знаком минус", p.x + 20, p.y + 312, (150, 150, 180), g.small)
        if s.msg: g.txt(s.msg, p.x + 20, p.y + 330, (140, 240, 170), g.small)
