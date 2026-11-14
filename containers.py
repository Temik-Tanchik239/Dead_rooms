"""Ящики и сундуки: стоят на карте, не пропускают игрока, ломаются от ударов (или открываются на E) и роняют предметы с шансом.

Типы описаны в data/containers.json (размер, прочность, как открывается, картинки, содержимое по умолчанию).
Расстановка и содержимое каждого ящика задаются в редакторе карт и лежат в JSON карты, поле "containers":
    {"type": "wooden_crate", "x": 12, "y": 20, "chance": 1.0, "loot_mode": "independent", "hp": 30,
     "loot": [{"item": "random_weapon", "chance": 0.15, "min": 1, "max": 1}, {"item": "stub_artifact_red", "chance": 0.5}]}
  type       — id типа из data/containers.json;
  x, y       — НИЖНЯЯ ЛЕВАЯ клетка ящика (ящик 2×2 занимает клетки x..x+1 и y-1..y);
  chance     — шанс, что ящик вообще появится при входе на карту (0..1, по умолчанию 1);
  loot       — что выпадает (нет поля — берётся "loot" типа); item — id оружия, id предмета из assets/inventory.json -> items
               или "random_weapon" (случайное оружие героя); chance — шанс 0..1; min/max — сколько штук;
  loot_mode  — "independent": каждый пункт бросает свой шанс; "pick_one": выпадает не более одного пункта (шансы — доли от 1);
  hp         — прочность вместо прочности типа.

Как устроено:
  • клетки ящика в физической сетке карты (room.g) — стена "#": игрок, враги и пули его не проходят; сломали — клетки освобождаются;
  • объект ящика «как моб» (hp, rect, cx, cy, hurt, d ...), поэтому ближний бой, снаряды, заклинания, ноты барда и гарпуны бьют по нему
    тем же кодом, что и по мобам. В список room.mobs он не входит (двери, опыт и зачистка комнаты от него не зависят);
  • interact: "break" — только ломается; "open" — открывается на E (удары не вредят), остаётся стоять открытым; "both" — и то, и другое;
  • сломали нижний ящик стопки — верхние падают (settle); в сети всё считает хост, клиентам уходит состояние room.containers (state/apply_state).
"""
import random
import pygame as pg
from core import CFG, T, floor_below
from anim import sprite, ASSETS_EXISTS

DEFAULTS = {"name": "Ящик", "w": 1, "h": 1, "hp": 20, "interact": "break", "skin": "", "skin_open": "", "draw": None, "offset": [0, 0],
            "color": [150, 105, 60], "loot_mode": "independent", "loot": [], "spread": 22, "open_text": "Открыть", "reach": 30,
            "hit_flash": 0.12, "empty_text": ""}
RANDOM_WEAPON = "random_weapon"
ROLL_SPAWN = True   # бросать ли шанс появления ящика. Клиент сетевой игры выключает: какие ящики есть, говорит хост (state/apply_state)

def types():
    """Все типы ящиков: id -> описание (data/containers.json, ключ "containers")."""
    d = CFG.get("containers") or {}
    return d.get("containers", {}) if isinstance(d, dict) else {}

def type_def(tid):
    """Описание типа с подставленными значениями по умолчанию."""
    d = dict(DEFAULTS); d.update(types().get(tid, {})); return d

# ---------------- содержимое ----------------
def roll_loot(loot, mode="independent", rng=random):
    """Бросок содержимого -> список id предметов (с повторами, если выпало несколько штук). Неизвестные предметы пропускаются."""
    entries = [e for e in (loot or []) if isinstance(e, dict) and e.get("item")]
    picked = []
    if mode == "pick_one":   # не более одного пункта: шансы — доли от 1 (если сумма больше 1, нормируются)
        total = sum(max(0.0, float(e.get("chance", 1))) for e in entries); scale = max(1.0, total); x = rng.random() * scale; acc = 0.0
        for e in entries:
            acc += max(0.0, float(e.get("chance", 1)))
            if x < acc: picked = [e]; break
    else:
        picked = [e for e in entries if rng.random() < float(e.get("chance", 1))]
    out = []
    for e in picked:
        lo = max(1, int(e.get("min", 1))); hi = max(lo, int(e.get("max", lo)))
        for _ in range(rng.randint(lo, hi)):
            wid = _resolve(e["item"])
            if wid: out.append(wid)
    return out

def _resolve(item):
    """random_weapon -> случайное оружие героя (None, если герою оно не выпадает); иначе id, если такой предмет есть в игре."""
    import inventory
    from maps import random_weapon
    if item == RANDOM_WEAPON: return random_weapon()
    return item if inventory.is_item(item) else None

# ---------------- объект ящика ----------------
class Container:
    """Живой ящик/сундук комнаты. Поля hp, rect, cx, cy, d, hurt() — как у моба, см. docstring модуля."""
    is_container = True
    flies = False

    def __init__(s, room, uid, spec):
        d = type_def(spec.get("type")); s.room, s.uid, s.type, s.spec, s.def_ = room, uid, spec.get("type"), spec, d
        cw, ch = max(1, int(d["w"])), max(1, int(d["h"])); c0, r0 = int(spec["x"]), int(spec["y"])
        s.cells = [(c0 + i, r0 - j) for j in range(ch) for i in range(cw)]
        s.x, s.y, s.w, s.h = c0 * T, (r0 - ch + 1) * T, cw * T, ch * T
        s.maxhp = s.hp = float(spec.get("hp", d["hp"]))
        s.loot = spec.get("loot") if isinstance(spec.get("loot"), list) else d["loot"]
        s.loot_mode = spec.get("loot_mode", d["loot_mode"])
        s.opened = False; s.hit_t = -10_000; s.dy = 0   # dy — на сколько клеток ящик упал вниз (когда сломали опору)
        s.d = {"name": d["name"], "cc_immune": True}   # s.d читают заклинания и статусы (status.cc_immune): ящик нельзя оглушить или схватить
        s.vx = s.vy = 0.0; s.stun = s.frozen = s.burn = s.burn_dps = 0.0; s.aggro = False; s.act = None; s.grav = None; s.state = "idle"; s.dir = 1; s.flash = 0.0

    def shift(s, n):
        """Сдвинуть ящик на n клеток вниз (падение). Клетки в сетке карты обновляет вызывающий (settle / apply_state)."""
        s.y += n * T; s.cells = [(c, r + n) for c, r in s.cells]; s.dy += n

    @property
    def rect(s): return pg.Rect(int(s.x), int(s.y), s.w, s.h)
    @property
    def cx(s): return s.x + s.w / 2
    @property
    def cy(s): return s.y + s.h / 2
    @property
    def can_break(s): return s.def_["interact"] in ("break", "both")
    @property
    def can_open(s): return s.def_["interact"] in ("open", "both") and not s.opened

    def hurt(s, dmg, kb, fx):
        """Удар (ближний бой, пуля, заклинание...). Сундук, который только открывается, урона не получает."""
        s.hit_t = pg.time.get_ticks()
        if not s.can_break: return
        s.hp -= dmg; fx.stop = max(fx.stop, .04); fx.text(str(max(1, int(dmg))), s.cx, s.y)

    # ---------- рисование ----------
    def draw(s, v):
        d, r = s.def_, s.rect; now = pg.time.get_ticks(); hot = now - s.hit_t < d["hit_flash"] * 1000
        sh = round(((now - s.hit_t) < 160) * ((-1) ** (now // 30)) * 2)   # короткая тряска после удара
        path = d["skin_open"] if s.opened and d["skin_open"] else d["skin"]
        dw, dh = d["draw"] or [r.w, r.h]; ox, oy = d["offset"]; img = sprite(path, int(dw), int(dh), False, hot) if path and ASSETS_EXISTS(path) else None
        x, y = r.centerx - int(dw) // 2 + int(ox) + sh, r.bottom - int(dh) + int(oy)
        if img: v.blit(img, (x, y))
        else: s._draw_default(v, r.move(sh, 0), hot)
        if s.can_break and s.hp < s.maxhp:   # полоска прочности над повреждённым ящиком
            bw = r.w - 8; fill = max(0.0, s.hp / s.maxhp)
            pg.draw.rect(v, (20, 16, 16), (r.x + 4, r.y - 8, bw, 4)); pg.draw.rect(v, (225, 90, 70), (r.x + 4, r.y - 8, int(bw * fill), 4))

    def _draw_default(s, v, r, hot):
        """Запасной рисунок без картинок: деревянный ящик с досками или сундук."""
        col = (255, 255, 255) if hot else tuple(s.def_["color"]); dark = tuple(int(c * .55) for c in col)
        pg.draw.rect(v, col, r.inflate(-2, -2), border_radius=3); pg.draw.rect(v, dark, r.inflate(-2, -2), 2, border_radius=3)
        if s.def_["interact"] == "break": pg.draw.line(v, dark, r.topleft, r.bottomright, 2); pg.draw.line(v, dark, r.topright, r.bottomleft, 2)
        else:
            pg.draw.line(v, dark, (r.x + 2, r.centery), (r.right - 2, r.centery), 3)
            pg.draw.rect(v, (225, 190, 80), (r.centerx - 4, r.centery - 5, 8, 10), border_radius=2)
            if s.opened: pg.draw.rect(v, (20, 14, 10), (r.x + 5, r.y + 3, r.w - 10, r.h // 2 - 4), border_radius=2)

# ---------------- комната ----------------
def create(room):
    """Ящики карты из room.d["containers"] (вызывается из GameMap.__init__): учитывает шанс появления и не ставит ящик на стену,
    в выход, на точку старта игрока и за край карты."""
    out, taken = [], set()
    protected = {(c, r) for c, r, e in room.cells() if e.get("player") or "exit" in e or e["type"] in ("wall", "ladder")}
    for uid, spec in enumerate(room.d.get("containers") or []):
        if not isinstance(spec, dict) or spec.get("type") not in types(): continue
        try: ct = Container(room, uid, spec)
        except (KeyError, TypeError, ValueError): continue
        if any(not (0 <= c < room.width and 0 <= r < room.height) or (c, r) in protected or (c, r) in taken for c, r in ct.cells): continue
        if ROLL_SPAWN and random.random() >= float(spec.get("chance", 1.0)): continue
        taken.update(ct.cells); out.append(ct)
    return out

def block(room):
    """Клетки живых ящиков — стена в физической сетке (вызывается из GameMap.build, который строит её заново)."""
    for ct in room.containers:
        for c, r in ct.cells: room.g[r][c] = "#"

def release(room, ct):
    """Освободить клетки ящика (сломан): вернуть физику клетки карты."""
    for c, r in ct.cells: room.g[r][c] = room.base_cell(c, r)

def _supported(room, ct):
    """Есть ли под ящиком опора: пол, платформа, дверь или другой ящик (хотя бы под одной его клеткой)."""
    low = max(r for _, r in ct.cells) + 1
    return any(low >= len(room.g) or room.g[low][c] in "#=D" for c in {c for c, _ in ct.cells})

def settle(room):
    """Ящики без опоры (нижний в стопке сломан) падают вниз до пола или другого ящика."""
    moved = True
    while moved:
        moved = False
        for ct in sorted(room.containers, key=lambda c: -c.y):
            if _supported(room, ct): continue
            release(room, ct); ct.shift(1); moved = True
            for c, r in ct.cells: room.g[r][c] = "#"

def remove(room, ct):
    if ct in room.containers: room.containers.remove(ct)
    release(room, ct); settle(room)

def drop_loot(room, ct, fx):
    """Выбросить содержимое: предметы кучкой на полу под ящиком."""
    from maps import Drop
    items = roll_loot(ct.loot, ct.loot_mode); n = len(items); spread = float(ct.def_["spread"])
    if not items and ct.def_["empty_text"]: fx.text(ct.def_["empty_text"], ct.cx, ct.y - 14)
    for i, wid in enumerate(items):
        x = max(ct.x + 6, min(ct.x + ct.w - 6, ct.cx + (i - (n - 1) / 2) * spread))
        gy = floor_below(room.g, x, ct.y + ct.h - 2); y = (gy if gy is not None else ct.y + ct.h) - 14
        room.drops.append(Drop(x, y, wid))

def break_container(room, ct, fx):
    """Ящик сломан: освобождаем клетки, эффекты, выпадает содержимое (из открытого сундука уже ничего не выпадет)."""
    remove(room, ct)
    col = tuple(ct.def_["color"]); fx.flash(ct.cx, ct.cy, max(ct.w, ct.h) * .8, col); fx.ring(ct.cx, ct.cy, max(ct.w, ct.h) * .7); fx.shake = max(fx.shake, .08)
    if not ct.opened: drop_loot(room, ct, fx)

def sweep(room, fx):
    """Каждый кадр на хосте/в одиночной игре: сломать всё, у чего кончилась прочность (урон мог прийти откуда угодно: удар, пуля, нота...)."""
    for ct in list(room.containers):
        if ct.hp > 0: continue
        if ct.can_break: break_container(room, ct, fx)
        else: ct.hp = ct.maxhp   # «только открывается»: урон его не ломает

def open_container(room, ct, fx):
    """Открыть сундук на E: содержимое выпадает, сундук остаётся стоять открытым. False — открыть нельзя."""
    if not ct.can_open: return False
    ct.opened = True; fx.flash(ct.cx, ct.y + 6, 36, (255, 220, 140)); drop_loot(room, ct, fx); return True

def try_open(room, pl, fx):
    """E рядом с открываемым сундуком. True — что-то открыли."""
    for ct in room.containers:
        if ct.can_open and ct.rect.inflate(2 * int(ct.def_["reach"]), 24).colliderect(pl.rect): return open_container(room, ct, fx)
    return False

def draw(room, v):
    for ct in room.containers: ct.draw(v)

def draw_prompts(v, room, pl, font):
    """Подсказка «[E] Открыть» над сундуком рядом с героем."""
    for ct in room.containers:
        if ct.can_open and ct.rect.inflate(2 * int(ct.def_["reach"]), 24).colliderect(pl.rect):
            t = font.render("[E] " + str(ct.def_["open_text"]), True, (255, 230, 120)); v.blit(t, (ct.cx - t.get_width() // 2, ct.y - 30))

# ---------------- сеть ----------------
def state(room):
    """Состояние для снимка игры: {uid: [прочность, открыт]} живых ящиков (JSON-совместимо)."""
    return {str(ct.uid): [round(ct.hp, 1), int(ct.opened), ct.dy] for ct in room.containers}

def apply_state(room, st):
    """Клиент: привести ящики комнаты к состоянию хоста (нет в списке — сломан или не появился на хосте)."""
    if not isinstance(st, dict): return
    for ct in list(room.containers):
        v = st.get(str(ct.uid))
        if v is None: remove(room, ct); continue
        hp, opened = float(v[0]), bool(v[1])
        if hp < ct.hp: ct.hit_t = pg.time.get_ticks()
        ct.hp, ct.opened = hp, opened
        if len(v) > 2 and int(v[2]) > ct.dy:   # хост уронил ящик ниже, чем успели мы
            release(room, ct); ct.shift(int(v[2]) - ct.dy)
            for c, r in ct.cells: room.g[r][c] = "#"
