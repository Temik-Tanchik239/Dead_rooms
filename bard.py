"""Бард (герой «Бард»): вместо оружия — гитара. Выбираешь ноту и играешь её, пока зажата ЛКМ (или J): эффект ноты расходится вокруг барда.

Включается полем "bard" героя в data/characters.json (нет поля — модуль ничего не делает):
    "bard": {
        "guitar": {"skin": "weapons/guitar.png", "draw": [46, 23],   # картинка гитарой вправо (грифом) и размер на экране
                   "grip": [12, 12],        # где рука держит корпус, px от левого верхнего угла картинки (в размере draw)
                   "hand": [6, -19],        # куда на герое: вперёд по взгляду и вверх от ног, px
                   "angle": 24,             # наклон грифа вверх (градусы), пока не играет
                   "bob": 2.0, "swing": 7, "rate": 3.2},   # при игре: покачивание (px), раскачка (градусы) и темп (удары в секунду)
        "notes": ["note_heal", "note_mana", "note_stun", "note_damage"]   # ноты по порядку — навыки category "note" из data/skills.json
    }
Нота — запись в data/skills.json с "category": "note", "type": "note":
    effect   — что делает: "heal" (лечит барда и союзников в радиусе), "mana" (восстанавливает им ману), "stun" (оглушает всех врагов в радиусе:
               не двигаются и не атакуют, боссы не поддаются), "damage" (урон всем врагам в радиусе);
    radius   — радиус действия, px (умножается пассивкой «Эхо», type note_radius);
    tick     — период эффекта, сек; amount — сколько за тик (лечение/мана/урон; умножается пассивкой «Резонанс», type note_power), duration — на сколько
               оглушать за тик (стан обновляется, пока нота играет);
    mana_cost — мана В СЕКУНДУ, пока играет (0 — бесплатно); не хватает маны — нота обрывается, надо отпустить кнопку и нажать заново;
    color, icon, name, description — как у остальных навыков.
Выбор ноты — те же клавиши, что смена снарядов у арбалетчика (ammo1_prev / ammo1_next, 1/2): колонка нот у левого края экрана (hud.book_draw)
плавно прокручивается. Ноту нельзя играть в перекате, на лестнице и в оглушении.

Навык «Усилитель» (type "amp", @spell ниже): ставит на землю установку, которая, пока бард играет, повторяет ту же ноту вокруг себя
(радиус — radius_mult от радиуса ноты; цель, попавшая в оба круга, получает эффект один раз за тик). Поля: duration (сек жизни), max (сколько
усилителей одновременно; новый вытесняет старый), radius_mult, skin + draw [w, h] (картинка установки в assets). «Медиатор» — обычный
навык type "projectile" с пулей pick (aoe + effect {"stun": ...} в projectiles.json).

Состояние игрока: bd_note — индекс выбранной ноты, bd_play — играет ли сейчас, bd_tick — до следующего тика, bd_notice — вспышка смены (HUD),
bd_lock — мана кончилась, ждём отпускания кнопки, amps — установки [{x, y, t, life, sid, vy, ground}]. Эффекты на союзников нужен список игроков:
PLAYERS (None — только сам бард, одиночная игра; хост сети выставляет живых игроков на время обновления). Сеть: net_pack / net_apply
(хост шлёт в снимке игрока ключ "bd"); аура и гитара рисуются у всех из этого состояния."""
import math
import pygame as pg
from core import CFG, T, tile
from anim import sprite
import spells
import status
from spells import spell

PLAYERS = None   # кому достаются лечение/мана от нот: None — только самому барду; хост сетевой игры подставляет всех живых игроков
GUITAR = {"skin": "weapons/guitar.png", "draw": [46, 23], "grip": [12, 12], "hand": [6, -19], "angle": 24, "bob": 2.0, "swing": 7, "rate": 3.2}
_vis = {}        # id(игрок) -> [плавная «громкость» игры 0..1, прошлый тик]: сглаживание только для рисования (работает и для чужих героев в сети)


def cfg():
    return CFG.get("character", {}).get("bard") or {}


def enabled():
    """Бард ли текущий герой (CFG["character"])."""
    return bool(cfg())


def init(pl):
    """Поля барда на игроке (нужны всем героям — чтобы сетевой снимок и HUD не падали)."""
    pl.bd_note = 0; pl.bd_play = False; pl.bd_tick = 0.0; pl.bd_notice = 0.0; pl.bd_lock = False; pl.amps = []


def note_ids():
    """Ноты героя по порядку (только существующие в skills.json)."""
    defs = CFG.get("skills", {})
    return [sid for sid in cfg().get("notes", []) if sid in defs]


def current(pl):
    """id выбранной ноты (или None)."""
    ids = note_ids()
    return ids[pl.bd_note % len(ids)] if ids else None


def swap(pl, direction=1):
    """Листает ноты (+1 — следующая, −1 — предыдущая). Если бард играет, продолжает играть уже новую ноту."""
    ids = note_ids()
    if not enabled() or not ids: return False
    pl.bd_note = (pl.bd_note + direction) % len(ids); pl.bd_notice = 1.0; pl.bd_tick = 0.0
    return True


def guitar_cfg():
    return {**GUITAR, **(cfg().get("guitar") or {})}


def circles(pl, a):
    """Круги действия ноты a: вокруг барда и вокруг каждого усилителя — [(x, y, радиус)]."""
    r = float(a.get("radius", 130)) * pl.passive_mult("note_radius")
    out = [(pl.cx, pl.cy, r)]
    for amp in pl.amps:
        rm = float(CFG.get("skills", {}).get(amp.get("sid", "amp"), {}).get("radius_mult", 0.9))
        out.append((amp["x"], amp["y"] - 18, r * rm))
    return out


def _dot(m, dmg, fx):
    """Периодический урон моба без отскока и стоп-кадра (как горение): мигание и число урона, без «подпрыгивания» и заморозки игры."""
    if m.d.get("boss_visual") == "morgart":   # составной босс: части получают урон только через hurt
        stop = fx.stop; m.hurt(dmg, 0, fx); fx.stop = stop; return
    m.hp -= dmg; m.flash = max(getattr(m, "flash", 0.0), .08); m.aggro = True
    fx.text(str(max(1, int(dmg))), m.cx, m.y)


def apply_note(pl, a, mobs, fx):
    """Один тик ноты: эффект получают все цели, попавшие хотя бы в один из кругов (бард + усилители) — каждая по разу."""
    cs = circles(pl, a); power = pl.passive_mult("note_power"); kind = a.get("effect")
    players = PLAYERS if PLAYERS is not None else [pl]
    def hit_p(p): return any((p.cx - cx) ** 2 + (p.cy - cy) ** 2 <= r * r for cx, cy, r in cs)
    def hit_m(m): return any(spells._near(m, cx, cy, r) for cx, cy, r in cs)
    amount = float(a.get("amount", 0)) * power
    if kind == "heal":
        for p in players:
            if p.hp > 0 and p.hp < p.maxhp and hit_p(p):
                got = min(amount, p.maxhp - p.hp); p.hp += got
                if got >= 1: fx.text(f"+{int(round(got))}", p.cx, p.y - 6)
    elif kind == "mana":
        for p in players:
            if p.hp > 0 and p.mana < p.maxmana and hit_p(p):
                got = min(amount, p.maxmana - p.mana); p.mana += got
                if got >= 1: fx.text(f"+{int(round(got))}", p.cx, p.y - 6)
    elif kind == "stun":
        dur = float(a.get("duration", 0.9)) * power
        for m in mobs:
            if m.hp > 0 and hit_m(m):
                fresh = getattr(m, "stun", 0.0) <= 0.05
                status.apply(m, {"stun": dur}, None)   # без текста на каждый тик: подпись «оглушён» один раз, когда враг только попал под ноту
                if fresh and not status.cc_immune(m): fx.text("оглушён", m.cx, m.cy - 60)
    elif kind == "damage":
        dmg = amount * pl.dmg_mult()
        for m in mobs:
            if m.hp > 0 and hit_m(m): _dot(m, dmg, fx)


def update(pl, dt, g, mobs, fx, can, held):
    """Каждый кадр (из Player.update): играет ли бард, трата маны, тики эффекта, жизнь и падение усилителей.
    can — можно играть (обычное состояние, не оглушён); held — кнопка игры зажата."""
    pl.bd_notice = max(0.0, pl.bd_notice - dt)
    if dt <= 0: return
    sid = current(pl); a = CFG.get("skills", {}).get(sid) if sid else None
    if not held: pl.bd_lock = False
    want = bool(a) and held and can and not pl.bd_lock
    if want:
        cost = float(a.get("mana_cost", 0))
        if cost > 0:
            if not pl.bd_play and pl.mana < max(1.0, cost * 0.3):   # на старт нужно хоть немного маны
                pl.mana_flash = .35; pl.bd_lock = True; want = False
            else:
                pl.mana = max(0.0, pl.mana - cost * dt); pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
                if pl.mana <= 0: pl.mana_flash = .35; pl.bd_lock = True; want = False
    if want and not pl.bd_play: pl.bd_tick = 0.0   # первый тик — сразу, как только заиграл
    pl.bd_play = want
    if want:
        pl.bd_tick -= dt
        if pl.bd_tick <= 0:
            pl.bd_tick = max(0.1, float(a.get("tick", 0.5)))
            apply_note(pl, a, mobs, fx)
    _amps_update(pl, dt, g)


def _amps_update(pl, dt, g):
    """Усилители: время жизни и падение на землю (плоский пол и платформы), за краем карты — пропадают."""
    keep = []
    for amp in pl.amps:
        amp["t"] -= dt
        if amp["t"] <= 0: continue
        col = int(amp["x"] // T)
        if not amp.get("ground"):
            if tile(g, col, int(amp["y"] // T)) in "#D=": amp["ground"] = True   # уже стоит на полу/платформе
            else:
                amp["vy"] = amp.get("vy", 0.0) + 1600 * dt; ny = amp["y"] + amp["vy"] * dt; row = int(ny // T)
                if row > int(amp["y"] // T) and tile(g, col, row) in "#D=": amp["y"] = row * T; amp["ground"] = True; amp["vy"] = 0.0
                else: amp["y"] = ny
        if amp["y"] > len(g) * T + 200: continue
        keep.append(amp)
    pl.amps = keep


def on_room_change(pl):
    """Смена комнаты: усилители остаются позади, игра прекращается."""
    pl.amps = []; pl.bd_play = False; pl.bd_lock = False


# ---------------- навык «Усилитель» ----------------

@spell("amp")
def _amp(pl, a, mobs, projs, fx):
    """Ставит усилитель перед бардом (он сам упадёт на землю). Одновременно действует max штук, новый вытесняет самый старый."""
    life = max(1.0, float(a.get("duration", 20.0)))
    x, y = pl.cx + pl.face * 28, pl.y + pl.h
    pl.amps.append({"x": x, "y": y, "t": life, "life": life, "sid": a.get("_sid", "amp"), "vy": 0.0, "ground": False})
    del pl.amps[:-max(1, int(a.get("max", 1)))]
    fx.ring(x, y - 18, 40)


# ---------------- рисование ----------------

def _now():
    return pg.time.get_ticks() / 1000.0


def _volume(pl):
    """Плавная «громкость» игры 0..1 для рисования (нарастает при игре, затухает после); считается по настенному времени, не по update."""
    now = _now(); st = _vis.setdefault(id(pl), [0.0, now]); dt = min(0.1, max(0.0, now - st[1])); st[1] = now
    st[0] += ((1.0 if pl.bd_play else 0.0) - st[0]) * (1 - math.exp(-dt * 8)); return st[0]


def _glyph(surf, x, y, s, col):
    """Маленькая восьмая нота (♪) на поверхности: головка, штиль, хвостик."""
    pg.draw.ellipse(surf, col, (x - s * .45, y - s * .2, s * .8, s * .55))
    pg.draw.line(surf, col, (x + s * .3, y + s * .05), (x + s * .3, y - s * 1.05), max(1, int(s * .18)))
    pg.draw.polygon(surf, col, [(x + s * .3, y - s * 1.05), (x + s * .85, y - s * .7), (x + s * .75, y - s * .35), (x + s * .3, y - s * .6)])


def draw_world(v, pl):
    """Аура играющей ноты (мягкий круг, расходящиеся кольца, плывущие вверх ноты) вокруг барда и усилителей + сами усилители. Рисуется под героем."""
    sid = current(pl); a = CFG.get("skills", {}).get(sid) if sid else None; vol = _volume(pl); t = _now()
    defs = CFG.get("skills", {})
    for amp in pl.amps:   # установки — картинка (hook в skills.json: skin + draw) и полоска оставшегося времени
        ad = defs.get(amp.get("sid", "amp"), {}); dw, dh = ad.get("draw", [40, 44]); img = sprite(ad.get("skin", "skills/amp.png"), dw, dh)
        blink = amp["t"] < 3.0 and int(t * 6) % 2 == 0   # последние секунды мигает
        if img and not blink: v.blit(img, (int(amp["x"] - dw / 2), int(amp["y"] - dh)))
        elif not img: pg.draw.rect(v, (70, 70, 84), (int(amp["x"] - 14), int(amp["y"] - 30), 28, 30))
        frac = max(0.0, min(1.0, amp["t"] / max(0.1, amp.get("life", amp["t"]))))
        pg.draw.rect(v, (24, 18, 26), (int(amp["x"] - 15), int(amp["y"] - dh - 7), 30, 5)); pg.draw.rect(v, (255, 190, 90), (int(amp["x"] - 14), int(amp["y"] - dh - 6), int(28 * frac), 3))
    if not a or vol < 0.02: return
    col = tuple(a.get("color", [255, 255, 255]))[:3]
    for cx, cy, r in circles(pl, a):
        size = int(r * 2 + 8); s = pg.Surface((size, size), pg.SRCALPHA); c = size // 2
        pg.draw.circle(s, (*col, int(36 * vol)), (c, c), int(r))
        pg.draw.circle(s, (*col, int(150 * vol)), (c, c), int(r * (0.97 + 0.03 * math.sin(t * 5))), 2)
        for k in range(2):   # расходящиеся кольца
            p = (t * 0.9 + k * 0.5) % 1.0
            pg.draw.circle(s, (*col, int(90 * vol * (1 - p))), (c, c), max(2, int(r * p)), 2)
        for i in range(7):   # плывущие ноты
            p = (t * 0.7 + i / 7.0) % 1.0; ang = i * 2.4 + t * 0.6; rr = r * (0.2 + 0.72 * p)
            _glyph(s, c + math.cos(ang) * rr, c + math.sin(ang) * rr * 0.8 - 18 * p, 9, (*col, int(210 * vol * math.sin(math.pi * p))))
        v.blit(s, (int(cx - c), int(cy - c)))


def draw_guitar(v, pl):
    """Гитара в руках: наклонена грифом вверх; пока играет — покачивается в такт. Картинка зеркалится при взгляде влево."""
    c = guitar_cfg(); vol = _volume(pl); t = _now(); f = pl.face
    dw, dh = c["draw"]; gx, gy = c["grip"]; hx, hy = c["hand"]
    beat = math.sin(t * c["rate"] * 2 * math.pi)
    ang = c["angle"] + c["swing"] * vol * math.sin(t * c["rate"] * 2 * math.pi + 1.0)
    px, py = pl.rect.centerx + f * hx, pl.rect.bottom + hy + c["bob"] * vol * beat
    q = round((ang if f > 0 else -ang) / 5) * 5
    img = sprite(c["skin"], dw, dh, f < 0, False, q)
    if not img:
        ex, ey = px + f * math.cos(math.radians(ang)) * 30, py - math.sin(math.radians(ang)) * 30
        pg.draw.line(v, (30, 20, 20), (px, py), (ex, ey), 6); pg.draw.line(v, (204, 124, 52), (px, py), (ex, ey), 4); return
    th = math.radians(q); vx, vy = (gx if f > 0 else dw - gx) - dw / 2, gy - dh / 2
    rx, ry = vx * math.cos(th) + vy * math.sin(th), -vx * math.sin(th) + vy * math.cos(th)
    v.blit(img, img.get_rect(center=(int(px - rx), int(py - ry))))


# ---------------- сеть ----------------

def net_pack(pl):
    """В снимок игрока: [выбранная нота, играет ли, [[x, y, осталось, всего, id навыка], ...] — усилители]."""
    return [int(pl.bd_note), int(bool(pl.bd_play)), [[round(a["x"]), round(a["y"]), round(a["t"], 1), round(a.get("life", a["t"]), 1), a.get("sid", "amp")] for a in pl.amps]]


def net_apply(pl, bd, local=False):
    """Применить пришедшее от хоста. Нота и усилители — решение хоста; «играет» у своего героя с предсказанием считаем сами."""
    if not isinstance(bd, list) or len(bd) < 3: return
    try: pl.bd_note = int(bd[0])
    except (TypeError, ValueError): return
    if not local: pl.bd_play = bool(bd[1])
    amps = []
    try:
        for it in bd[2][:4]: amps.append({"x": float(it[0]), "y": float(it[1]), "t": float(it[2]), "life": float(it[3]), "sid": str(it[4]), "vy": 0.0, "ground": True})
    except (TypeError, ValueError, IndexError): amps = []
    pl.amps = amps
