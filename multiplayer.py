"""Мультиплеер по локальной сети (LAN).

Как устроено
  * Хост считает весь мир: карты, мобов, пули и ВСЕХ игроков. Клиенты присылают хосту только своё управление
    (зажатые клавиши, прицел мыши, нажатия), а каждый кадр получают от хоста снимок мира и рисуют его.
    Так у всех одна и та же игра и не бывает рассинхрона.
  * TCP-порт 5555 — игра; UDP-порт 5556 — поиск игр в локальной сети (кнопка «Подключиться» показывает найденных хостов).
  * Сообщение = 4 байта длины + JSON, сжатый zlib. Никакого pickle — чужие данные из сети не исполняются.

Механики в сетевой игре
  * Отряд ходит по картам вместе: кто первым зашёл в выход, тот переводит на следующую карту всех.
  * Двери запираются, только когда ВСЕ живые игроки отошли от входа (никто не застрянет в двери).
  * Мобы выбирают ближайшего живого игрока; удары по площади и вражеские пули задевают всех.
  * Опыт за убитого моба получает каждый игрок, уровни и навыки — у каждого свои.
  * Оружие на полу подбирает тот, кто нажал E рядом. Награда за зачистку падает рядом со случайным игроком.
  * Игрок с нулём HP падает. Союзник, постоявший рядом 3 секунды, поднимает его (35% HP);
    зачистка карты поднимает всех павших (25% HP). Погибли все — хост нажимает R, начинается новый забег.
  * Пауза (Esc), карта мира (M) и настройки не останавливают сетевую игру — персонаж в это время стоит.
  * Подключиться можно и во время забега: новый игрок появляется рядом с союзниками.
"""
import hashlib, json, math, queue, random, socket, struct, threading, time, zlib
from collections import deque
from types import SimpleNamespace
import pygame as pg
from core import CFG, SETTINGS, T, W, VIEW_H, CHAR, use_char, apply_character, char_ids, char_def, approach, tile, free, FX
import characters as char_menu
from maps import Campaign, Drop, END, random_weapon
from mob import Mob, Corpse, normalize, spawn_boss, scale_boss_for_players
from projectiles import Proj
from attacks import ATTACKS
from anim import sprite, mob_frame

PORT = 5555                 # TCP: игра
DISCOVERY_PORT = 5556       # UDP: поиск хостов в локальной сети
PROTO = 1                   # версия сетевого протокола
MAX_PLAYERS = 4
REVIVE_TIME = 3.0           # сколько секунд стоять рядом с павшим союзником, чтобы поднять его
REVIVE_RADIUS = (56, 64)
REVIVE_HP, CLEAR_REVIVE_HP = .35, .25
SPREAD = (0, -18, 18, -36)  # сдвиг игроков по x при появлении на карте
COLORS = ((255, 214, 92), (110, 200, 255), (140, 235, 140), (240, 130, 200))
MENU_MODES = ("mp", "connect")
_PING, _PONG = b"DEADROOMS?", b"DEADROOMS!"


# ======================================================================
#  Сеть: сообщения, соединение, сервер, поиск хостов
# ======================================================================
def pack(msg):
    body = zlib.compress(json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 1)
    return struct.pack(">I", len(body)) + body


def content_sig():
    """Отпечаток игровых данных: у хоста и клиента должны совпадать карты, мобы, оружие и герои."""
    parts = [sorted(CFG["map_defs"]), sorted(CFG["mobs"]), sorted(CFG["weapons_base"]), sorted(CFG["projectiles"]),
             sorted(CFG["skills_base"]), char_ids()]
    return hashlib.md5(json.dumps(parts).encode("utf-8")).hexdigest()[:12]


def default_name():
    try: name = socket.gethostname().split(".")[0]
    except OSError: name = ""
    return (name or "Игрок")[:16]


def local_ips():
    """IPv4-адреса этого компьютера в локальной сети (первый — основной)."""
    ips = []
    try:
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.connect(("10.255.255.255", 1))   # пакет не отправляется — так узнаём адрес основного интерфейса
        ips.append(u.getsockname()[0]); u.close()
    except OSError: pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if info[4][0] not in ips: ips.append(info[4][0])
    except OSError: pass
    ips = [ip for ip in ips if not ip.startswith(("127.", "0."))]
    return ips or ["127.0.0.1"]


def parse_address(text):
    """'192.168.1.5' или '192.168.1.5:5555' -> (host, port) или (None, ошибка)."""
    text = text.strip()
    if not text: return None, "Введите IP-адрес хоста"
    host, port = text, PORT
    if text.count(":") == 1:
        host, p = text.split(":")
        try: port = int(p)
        except ValueError: return None, "Порт должен быть числом"
        if not 0 < port < 65536: return None, "Порт должен быть от 1 до 65535"
    host = host.strip()
    if not host: return None, "Введите IP-адрес хоста"
    return (host, port), None


class Conn:
    """TCP-соединение: поток чтения складывает сообщения в inbox, поток записи отправляет очередь.
    Снимки мира не копятся: если сеть не успевает, старый снимок заменяется свежим."""
    def __init__(s, sock):
        s.sock = sock
        try: sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError: pass
        sock.settimeout(None)
        s.inbox = queue.Queue(); s.alive = True; s.closing = False
        s.cv = threading.Condition(); s.out = deque(); s.snap = None
        threading.Thread(target=s._reader, daemon=True).start()
        threading.Thread(target=s._writer, daemon=True).start()

    def send(s, msg): s.send_raw(pack(msg))
    def send_raw(s, data, snapshot=False):
        if not s.alive: return
        with s.cv:
            if snapshot: s.snap = data
            else: s.out.append(data)
            s.cv.notify()

    def _recv_exact(s, n):
        buf = b""
        while len(buf) < n:
            chunk = s.sock.recv(n - len(buf))
            if not chunk: raise ConnectionError("closed")
            buf += chunk
        return buf

    def _reader(s):
        try:
            while s.alive:
                n = struct.unpack(">I", s._recv_exact(4))[0]
                if n > 8_000_000: raise ConnectionError("слишком большое сообщение")
                msg = json.loads(zlib.decompress(s._recv_exact(n)).decode("utf-8"))
                if isinstance(msg, dict): s.inbox.put(msg)
        except (OSError, ConnectionError, ValueError, zlib.error, struct.error):
            pass
        s._dead()

    def _writer(s):
        while True:
            with s.cv:
                while s.alive and not s.out and s.snap is None and not s.closing: s.cv.wait(.5)
                if not s.alive: return
                items = list(s.out); s.out.clear(); snap, s.snap = s.snap, None
                closing = s.closing and not items and snap is None
            if closing: s._dead(); return
            try:
                for d in items: s.sock.sendall(d)
                if snap is not None: s.sock.sendall(snap)
            except OSError:
                s._dead(); return

    def _dead(s):
        if not s.alive: return
        s.alive = False
        try: s.sock.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        try: s.sock.close()
        except OSError: pass
        s.inbox.put({"t": "_closed"})
        with s.cv: s.cv.notify_all()

    def close(s, flush=False):
        """flush=True — сначала отправить всё из очереди (например, причину отказа), потом закрыть."""
        if flush and s.alive:
            with s.cv: s.closing = True; s.cv.notify()
        else: s._dead()


class Server:
    """Принимает подключения (TCP) и отвечает на поиск в локальной сети (UDP)."""
    def __init__(s, port, info):
        s.alive = True; s.info = info; s.new = queue.Queue()
        s.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):   # Windows: второй хост на том же порту получит понятную ошибку
            s.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for attempt in range(12):   # только что закрытое лобби освобождает порт не мгновенно
            try: s.sock.bind(("", port)); break
            except OSError:
                if attempt == 11: s.sock.close(); raise
                time.sleep(.1)
        s.sock.listen(8); s.sock.settimeout(.25)
        threading.Thread(target=s._accept, daemon=True).start()
        s.udp = None
        try:
            s.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.udp.bind(("", DISCOVERY_PORT)); s.udp.settimeout(.25)
            threading.Thread(target=s._discovery, daemon=True).start()
        except OSError:   # порт поиска занят (например, второй хост на этом же компьютере) — играть можно по IP
            s.udp = None

    def _accept(s):
        while s.alive:
            try: c, addr = s.sock.accept()
            except socket.timeout: continue
            except OSError: break
            if s.alive: s.new.put((Conn(c), addr))

    def _discovery(s):
        while s.alive:
            try: data, addr = s.udp.recvfrom(256)
            except socket.timeout: continue
            except OSError: break
            if data == _PING:
                try: s.udp.sendto(_PONG + json.dumps(s.info(), ensure_ascii=False).encode("utf-8"), addr)
                except OSError: pass

    def close(s):
        s.alive = False
        for sk in (s.sock, s.udp):
            if sk:
                try: sk.close()
                except OSError: pass


class Finder:
    """Ищет хосты в локальной сети широковещательным UDP-запросом раз в 1,5 секунды."""
    def __init__(s):
        s.found = {}; s.next_ping = 0.0; s.sock = None
        try:
            s.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sock.setblocking(False)
        except OSError: s.sock = None
        s.targets = ["255.255.255.255", "127.0.0.1"] + [ip.rsplit(".", 1)[0] + ".255" for ip in local_ips() if ip.count(".") == 3]

    def update(s):
        if not s.sock: return
        now = time.time()
        if now >= s.next_ping:
            s.next_ping = now + 1.5
            for addr in s.targets:
                try: s.sock.sendto(_PING, (addr, DISCOVERY_PORT))
                except OSError: pass
        for _ in range(64):
            try: data, addr = s.sock.recvfrom(2048)
            except (BlockingIOError, InterruptedError): break
            except ConnectionResetError: continue   # Windows: «порт недоступен» от прошлого запроса — пропускаем
            except OSError: break
            if not data.startswith(_PONG): continue
            try: info = json.loads(data[len(_PONG):].decode("utf-8"))
            except ValueError: continue
            ip = addr[0]
            if ip.startswith("127.") and any(not k.startswith("127.") and v[0].get("name") == info.get("name") for k, v in s.found.items()):
                continue   # свой же хост, уже найденный по сетевому адресу
            s.found[f"{ip}:{int(info.get('port', PORT))}"] = (info, now)
        s.found = {k: v for k, v in s.found.items() if now - v[1] < 5}

    def hosts(s):
        return sorted(((k, v[0]) for k, v in s.found.items()), key=lambda kv: kv[0])

    def close(s):
        if s.sock:
            try: s.sock.close()
            except OSError: pass
        s.sock = None


# ======================================================================
#  Управление
# ======================================================================
KEY_BITS = None
def _key_bits():
    global KEY_BITS
    if KEY_BITS is None:
        KEY_BITS = {pg.K_a: 0, pg.K_LEFT: 0, pg.K_d: 1, pg.K_RIGHT: 1, pg.K_w: 2, pg.K_UP: 2,
                    pg.K_s: 3, pg.K_DOWN: 3, pg.K_SPACE: 4}
    return KEY_BITS


class NetKeys:
    """Заменитель pg.key.get_pressed() для удалённого игрока: [влево, вправо, вверх, вниз, пробел]."""
    def __init__(s, bits=(0, 0, 0, 0, 0)):
        bits = list(bits)[:5]; bits += [0] * (5 - len(bits))
        s.bits = tuple(int(bool(b)) for b in bits)
    def __getitem__(s, key):
        i = _key_bits().get(key)
        return 0 if i is None else s.bits[i]


class Input:
    def __init__(s): s.keys = NetKeys(); s.aim = None; s.mb = (0, 0); s.pose = None


def local_bits(g):
    if g.overlay_open(): return [0, 0, 0, 0, 0]
    k = pg.key.get_pressed()
    return [int(bool(k[pg.K_a] or k[pg.K_LEFT])), int(bool(k[pg.K_d] or k[pg.K_RIGHT])), int(bool(k[pg.K_w] or k[pg.K_UP])),
            int(bool(k[pg.K_s] or k[pg.K_DOWN])), int(bool(k[pg.K_SPACE]))]


def local_aim(g):
    if g.overlay_open() or not SETTINGS.get("mouse_aim", True): return None
    mx, my = pg.mouse.get_pos()
    return (mx / g.zoom + g.cam[0], my / g.zoom + g.cam[1])


def local_mb(g):
    if g.overlay_open(): return (0, 0)
    mb = pg.mouse.get_pressed()
    return (int(bool(mb[0])), int(bool(mb[2])))


def _num(v, default=0.0):
    try:
        v = float(v)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError): return default


def clean_name(name, fallback="Игрок"):
    name = "".join(ch for ch in str(name or "") if ch.isprintable()).strip()[:16]
    return name or fallback


# ======================================================================
#  Общее для хоста и клиента
# ======================================================================
class Session:
    max_players = MAX_PLAYERS
    def __init__(s, g):
        s.g = g; s.players = {}; s.lobby = []; s.my_id = None; s.phase = "lobby"
        s.game_over = False; s.banner = None; s._track = None

    @property
    def in_game(s): return s.phase == "game" and s.ready

    def player_list(s): return list(s.players.values())
    def lobby_players(s): return list(s.lobby)
    def color_of(s, pid): return COLORS[int(pid or 0) % len(COLORS)]

    def track_local(s):
        """Повышение уровня своего игрока -> плашка вверху экрана (в сети игра не встаёт на паузу ради меню уровня)."""
        p = s.g.pl if s.in_game else None
        if p is None: return
        if s._track and s._track[0] == p.pid and p.level > s._track[1]:
            new = [sid for sid in p.skills if sid not in s._track[2]]
            with use_char(p.char_id):
                names = [CFG.get("skills", {}).get(sid, {}).get("name", sid) for sid in new]
            text = f"НОВЫЙ УРОВЕНЬ {p.level}" + (f" — открыт навык: {', '.join(names)}" if names else "")
            s.banner = (text, pg.time.get_ticks() + 3500)
        s._track = (p.pid, p.level, list(p.skills))


# ======================================================================
#  Хост
# ======================================================================
class HostSession(Session):
    is_host = True
    ready = True

    def __init__(s, g, name, port=PORT):
        super().__init__(g)
        s.port = port; s.my_id = 0; s.next_id = 1
        last = SETTINGS.get("last_character")
        s.lobby = [{"id": 0, "name": clean_name(name), "char": last if last in char_ids() else CHAR["id"]}]
        s.conns = {}; s.pending = []; s.inputs = {0: Input()}
        s.room_armed = False; s.respawn = None; s.warn_t = 0
        s.ips = local_ips()
        s.server = Server(port, s.public_info)   # OSError, если порт занят — сообщение покажет меню

    def public_info(s):
        return {"name": s.lobby[0]["name"] if s.lobby else "?", "port": s.port, "players": len(s.lobby),
                "max": MAX_PLAYERS, "phase": s.phase}

    def address_line(s):
        extra = f" (ещё: {', '.join(s.ips[1:3])})" if len(s.ips) > 1 else ""
        return f"Ваш IP: {s.ips[0]}:{s.port}{extra} — друзья вводят его в «Подключиться»"

    def entry(s, pid): return next((e for e in s.lobby if e["id"] == pid), None)

    # ---------- лобби ----------
    def set_char(s, cid):
        if cid in char_ids():
            s.lobby[0]["char"] = cid
            SETTINGS["last_character"] = cid; s.g.save_settings()
            s.broadcast_lobby()

    def broadcast_lobby(s):
        msg = pack({"t": "lobby", "players": s.lobby, "phase": s.phase})
        for c in s.conns.values(): c.send_raw(msg)

    def start(s):
        if s.phase != "lobby": return
        s.set_char(char_menu.selected(s.g))
        s.phase = "game"
        s.begin_run(0, fresh=True)
        for c in s.conns.values(): c.send({"t": "start"})
        s.broadcast_lobby()
        s.g.menu_mode = None

    # ---------- соединения ----------
    def accept(s):
        while True:
            try: conn, addr = s.server.new.get_nowait()
            except queue.Empty: break
            s.pending.append([conn, addr, time.time()])
        for item in s.pending[:]:
            conn, addr, t0 = item
            try: msg = conn.inbox.get_nowait()
            except queue.Empty:
                if time.time() - t0 > 5: conn.close(); s.pending.remove(item)
                continue
            s.pending.remove(item)
            if msg.get("t") != "hello": conn.close(); continue
            reason = None
            if msg.get("proto") != PROTO: reason = "Другая версия сетевой игры — обновите игру у всех игроков"
            elif msg.get("sig") != content_sig(): reason = "У хоста и у вас разные файлы игры (data/): карты, мобы, оружие или герои"
            elif len(s.lobby) >= MAX_PLAYERS: reason = f"Лобби заполнено ({MAX_PLAYERS} игрока)"
            if reason:
                conn.send({"t": "reject", "reason": reason}); conn.close(flush=True); continue
            pid = s.next_id; s.next_id += 1
            ids = char_ids()
            cid = msg.get("char") if msg.get("char") in ids else (ids[0] if ids else None)
            name = clean_name(msg.get("name"), f"Игрок {pid + 1}")
            if any(e["name"] == name for e in s.lobby): name = f"{name[:13]} {pid + 1}"
            s.lobby.append({"id": pid, "name": name, "char": cid}); s.conns[pid] = conn; s.inputs[pid] = Input()
            conn.send({"t": "welcome", "id": pid, "phase": s.phase, "name": name})
            if s.phase == "game": s.join_game(pid)
            s.broadcast_lobby()

    def process(s, pid, conn):
        for _ in range(200):
            try: msg = conn.inbox.get_nowait()
            except queue.Empty: return
            t = msg.get("t")
            if t in ("_closed", "bye"): s.drop(pid); return
            if t == "char" and s.phase == "lobby":
                e = s.entry(pid)
                if e and msg.get("char") in char_ids(): e["char"] = msg["char"]; s.broadcast_lobby()
            elif t == "in" and s.phase == "game":
                s.on_input(pid, msg)

    def on_input(s, pid, msg):
        inp = s.inputs.setdefault(pid, Input())
        k = msg.get("k")
        if isinstance(k, list): inp.keys = NetKeys(k)
        a = msg.get("aim")
        inp.aim = (_num(a[0]), _num(a[1])) if isinstance(a, list) and len(a) == 2 else None
        mb = msg.get("mb")
        if isinstance(mb, list) and len(mb) == 2: inp.mb = (int(bool(mb[0])), int(bool(mb[1])))
        pose = msg.get("pose")   # где клиент сам видит своего героя: [x, y, vx, vy, h, face, tp]
        inp.pose = [_num(v) for v in pose] if isinstance(pose, list) and len(pose) == 7 else None
        p = s.players.get(pid)
        for ev in (msg.get("ev") or [])[:24]:
            if p and p.hp > 0 and ev in s.g.ACTIONS: s.g.apply_action(p, ev)

    def drop(s, pid):
        conn = s.conns.pop(pid, None)
        if conn: conn.close()
        e = s.entry(pid)
        s.lobby = [x for x in s.lobby if x["id"] != pid]; s.inputs.pop(pid, None)
        p = s.players.pop(pid, None)
        if p is not None and s.g.fx: s.g.fx.text(f"{p.name} покинул игру", p.cx, p.y - 30)
        if e: s.broadcast_lobby()

    # ---------- забег ----------
    def make_player(s, pid):
        e = s.entry(pid)
        with use_char(e["char"]):
            p = s.g.Player()
        p.pid, p.name = pid, e["name"]
        return p

    def begin_run(s, loop, fresh):
        g = s.g
        apply_character(s.lobby[0]["char"])   # «свой» герой хоста — по умолчанию для HUD и меню
        if fresh:
            s.players = {e["id"]: s.make_player(e["id"]) for e in s.lobby}
        else:
            for p in s.players.values():
                if p.hp <= 0: p.hp = 0
                p.downed = False; p.revive = 0.0
                p.hp = min(p.maxhp, p.hp + 30); p.refresh_mana(True)
        # Новый круг — полностью новый набор комнат и мобов. Не переносим
        # сетевые идентификаторы/кэш противников из предыдущего круга.
        g.camp = Campaign(loop); g.room = None; g.done = False; g.fx = FX(); g.projs = []
        s.mobs = {}; s.room_armed = False; s.respawn = None
        g.level_menu = False; s.game_over = False
        g.pl = s.players[0]
        s.go(g.camp.first, None)

    def restart(s):
        if s.phase == "game" and s.game_over:
            s.begin_run(0, fresh=True)

    def next_loop(s):
        if s.phase == "game" and s.g.done:
            s.begin_run(s.g.camp.loop + 1, fresh=False)

    def join_game(s, pid):
        """Подключился во время забега — появляется рядом с живым союзником."""
        g = s.g; p = s.make_player(pid); r = g.room
        anchor = next((a for a in s.players.values() if a.hp > 0), None)
        if anchor: place(p, anchor_rect(anchor), anchor.state == "ladder", r, 0 if anchor.state == "ladder" else SPREAD[len(s.players) % len(SPREAD)] or 18)
        elif s.respawn: place(p, *s.respawn, r)
        p.armed = not r.exit_touch(p.rect)
        s.players[pid] = p
        g.fx.text(f"{p.name} присоединился", p.cx, p.y - 30)

    def go(s, mid, via):
        """Переход всего отряда на карту mid."""
        g = s.g; camp = g.camp; frm = g.room.id if g.room else None
        if frm and mid != frm: camp.came_from[mid] = frm
        r = g.room = camp.get(mid); r.visited = True; g.projs = []; r.corpses = []
        rect, ladder = r.arrival(frm, via, camp)
        s.respawn = (rect, ladder)
        for i, p in enumerate(s.players.values()):
            place(p, rect, ladder, r, 0 if ladder else SPREAD[i % len(SPREAD)]); p.armed = False
        s.room_armed = False
        if not r.spawned:
            r.mobs = []
            r.spawn()
            for mob in r.mobs: scale_boss_for_players(mob, len(s.players))   # босс с маркера B/C: здоровье растёт с числом игроков
            if r.cleared and camp.order and r.id == camp.order[-1] and not getattr(r, "boss_spawned", False):
                r.cleared = False
                players = list(s.players.values())
                s.clear(r, players, [p for p in players if p.hp > 0])

    def take_exit(s, z):
        g = s.g; r = g.room; target = g.camp.resolve(r.id, z["entry"]["exit"])
        if target == END: g.done = True; return True
        if target is None:
            if pg.time.get_ticks() > s.warn_t:
                g.fx.text(f"выход '{z['char']}' никуда не ведёт", z["rect"].centerx, z["rect"].y - 20); s.warn_t = pg.time.get_ticks() + 1500
            return False
        s.go(target, z["entry"]); return True

    def respawn_player(s, p):
        """Упал в пропасть. Если двери заперты, точка входа — внутри двери, поэтому ставим к союзнику."""
        g = s.g; r = g.room
        anchor = next((a for a in s.players.values() if a is not p and a.hp > 0), None)
        if r.locked and anchor: place(p, anchor_rect(anchor), False, r)
        else: place(p, *s.respawn, r)

    def clear(s, r, players, alive):
        g = s.g
        # Только хост вызывает clear(): босс создаётся один раз и попадает в сетевые снимки.
        order = g.camp.order
        if order and r.id == order[-1] and not getattr(r, "boss_spawned", False):
            boss = spawn_boss(r, g.camp.scale(), max(1, len(players)))
            if boss:
                r.boss_spawned = True; r.mobs.append(boss); r.set_lock(True)
                g.fx.text("БОСС ПРИБЫЛ!", sum(p.cx for p in (alive or players)) / max(1, len(alive or players)), min((p.y for p in (alive or players)), default=120) - 60)
                return
        r.cleared = True; r.set_lock(False)
        who = alive or players
        cx = sum(p.cx for p in who) / len(who); cy = min(p.y for p in who)
        g.fx.text("Зачищено!", cx - 30, cy - 60)
        rw = r.d.get("reward")
        if rw and random.random() < rw.get("chance", 1):
            p = random.choice(who)
            with use_char(p.char_id):
                wid = random_weapon() if rw.get("item", "random") == "random" else rw["item"]
                if wid in CFG["weapons"]: r.drops.append(Drop(p.cx, p.y + p.h - 14, wid))
        for p in players:
            if p.hp <= 0: s.revive(p, CLEAR_REVIVE_HP)

    def down(s, p):
        p.downed = True; p.revive = 0.0; p.state = "move"; p.atk = None; p.skill_cast = None; p.grab = None
        p.shield_time = 0.0; p.shield_hp = 0.0; p.hitbox = None; p.vx = 0
        if p.h != p.H0: p.y -= p.H0 - p.h; p.h = p.H0
        s.g.fx.text(f"{p.name} пал!", p.cx - 20, p.y - 30)

    def revive(s, p, frac):
        p.hp = max(1, round(p.maxhp * frac)); p.downed = False; p.revive = 0.0
        p.inv = 1.5; p.stun = 0; p.hp_regen_timer = 0.0; p.vx = p.vy = 0
        s.g.fx.text(f"{p.name} снова в бою!", p.cx - 30, p.y - 30)

    def feed_local(s):
        inp = s.inputs.setdefault(0, Input())
        inp.keys = NetKeys(local_bits(s.g)); inp.aim = local_aim(s.g); inp.mb = local_mb(s.g)

    def local_action(s, name):
        p = s.players.get(0)
        if p and p.hp > 0: s.g.apply_action(p, name)

    def step(s, dt):
        """Один кадр мира — как Game.step в одиночной игре, но для всех игроков сразу."""
        g = s.g; fx, r = g.fx, g.room
        fx.stop = 0; fx.shake = max(0, fx.shake - dt)   # общий «стоп-кадр» в сети выключен: он замораживал бы всех
        for it in fx.items: it[4] -= dt
        fx.items = [it for it in fx.items if it[4] > 0]
        players = list(s.players.values())
        s.game_over = bool(players) and all(p.hp <= 0 for p in players)
        if s.game_over: return
        s.feed_local()
        for p in players:
            if p.hp <= 0: continue
            inp = s.inputs.get(p.pid) or Input()
            p.aim = inp.aim
            if inp.mb[0]: p.press("a1")
            if inp.mb[1]: p.press("a2")
            p.update(dt, inp.keys, r.g, r.mobs, g.projs, fx); p.update_anim(dt)
            if inp.pose and p.pid != s.my_id:
                # Движение своего героя клиент считает сам (без задержки сети); хост между пакетами
                # продолжает его по последним клавишам, а пришедшее положение принимает как точное.
                x, y, vx, vy, h, face, tp = inp.pose; inp.pose = None
                if int(tp) == p.tp and not p.grab:      # схваченного героя держит рука босса — позу клиента не принимаем
                    p.x, p.y, p.vx, p.vy = x, y, vx, vy
                    p.h = int(max(4, min(p.H0, h))); p.face = 1 if face >= 0 else -1
        alive = [p for p in players if p.hp > 0]
        if alive:
            w = SimpleNamespace(g=r.g, pl=alive[0], players=alive, mobs=r.mobs, projs=g.projs, fx=fx)
            for m in r.mobs:
                w.pl = min(alive, key=lambda p: (p.cx - m.cx) ** 2 + (p.cy - m.cy) ** 2)   # моб видит ближайшего
                m.update(dt, w)
                if m.d.get("contact"):
                    for p in alive:
                        if p.hp > 0 and (m.touches_rect(p.rect) if hasattr(m, "touches_rect") else p.rect.colliderect(m.rect)): p.hit(m.d["contact"], m.cx, fx)
                xp = m.pop_xp() if hasattr(m, "pop_xp") else 0
                for p in players:
                    if xp: g.award_xp(p, xp, fx)          # опыт за уничтоженные руки босса
            for q in g.projs: q.update(dt, w)
        g.projs = [q for q in g.projs if not q.dead]
        for m in r.mobs:
            if m.hp <= 0:
                if not getattr(m, "xp_paid", False):
                    m.xp_paid = True
                    for p in players: g.award_xp(p, int(m.d.get("xp", 10)), fx)   # опыт получает каждый
                fx.ring(m.cx, m.cy, 28); c = Corpse(m)
                if not c.dead: r.corpses.append(c)
        for c in r.corpses: c.update(dt)
        r.corpses = [c for c in r.corpses if not c.dead]
        r.mobs = [m for m in r.mobs if m.hp > 0]
        for m in r.mobs:
            if m.y > r.height_px + 200 or m.y < -400 or m.x < -400 or m.x > r.width_px + 400: m.hp = 0
        for p in players:
            if p.hp <= 0 and not p.downed: s.down(p)
        alive = [p for p in players if p.hp > 0]
        if r.spawned and not r.cleared and not r.mobs: s.clear(r, players, alive); alive = [p for p in players if p.hp > 0]
        # павшие: падают на землю, союзник рядом поднимает
        for d in players:
            if d.hp > 0: continue
            with use_char(d.char_id):
                pc = CFG["player"]
                d.vx = approach(d.vx, 0, pc["friction"] * dt)
                d.vy = min(d.vy + pc["gravity"] * dt, pc["max_fall"])
            d.move(r.g, dt)
            if d.cy > r.height_px or d.cx < 0 or d.cx > r.width_px: s.respawn_player(d); d.vy = 0
            near = any(abs(a.cx - d.cx) < REVIVE_RADIUS[0] and abs(a.cy - d.cy) < REVIVE_RADIUS[1] for a in alive)
            d.revive = d.revive + dt if near else max(0.0, d.revive - dt)
            if d.revive >= REVIVE_TIME: s.revive(d, REVIVE_HP)
        alive = [p for p in players if p.hp > 0]
        for p in alive:
            sc, sr = int(p.cx // T), int((p.y + p.h - 2) // T)
            if tile(r.g, sc, sr) == "x": p.hit(r.spike_damage(sc, sr), p.cx, fx)
        # выходы: двери запираются, когда все живые отошли от входа; переход — для всего отряда
        for p in alive:
            if not p.armed and not r.exit_touch(p.rect): p.armed = True
        if not s.room_armed and alive and all(p.armed for p in alive):
            s.room_armed = True
            if r.mobs and r.d.get("lock", CFG["maps"].get("lock", True)): r.set_lock(True)
        for p in alive:
            z = r.exit_at(p.cx, p.cy)
            if p.armed and z is not None and s.take_exit(z): return
        for p in alive:
            if p.cx < 0 or p.cx > r.width_px or p.cy < 0 or p.cy > r.height_px:
                z = None if r.locked else (r.exit_at(p.cx, p.cy) or r.exit_near(p.rect))
                if z and s.take_exit(z): return
                if g.done: return
                p.hit(r.d.get("fall_damage", CFG["maps"].get("fall_damage", 15)), p.cx, fx); s.respawn_player(p)

    # ---------- снимок мира ----------
    def snapshot(s):
        g = s.g; r = g.room; R = lambda v: round(v, 1)
        styles, style_idx, projs = [], {}, []
        for q in g.projs:
            key = getattr(q, "_net_style", None)
            if key is None:
                st = {k: q.d[k] for k in ("frames", "fps", "skin", "sprite", "_id", "draw", "rotate", "color", "size") if k in q.d}
                st["size"] = q.r; st["color"] = list(q.color)
                key = q._net_style = json.dumps(st, sort_keys=True)
            if key not in style_idx: style_idx[key] = len(styles); styles.append(json.loads(key))
            if not hasattr(q, "nid"): q.nid = s.next_nid()
            projs.append([q.nid, R(q.x), R(q.y), R(q.vx), R(q.vy), round(q.t, 3), style_idx[key]])
        mobs = []
        for m in r.mobs:
            if not hasattr(m, "nid"): m.nid = s.next_nid();
            act = None
            if m.act:
                a = m.act; act = [a.get("i", 0), a["phase"], round(a["t"], 3)]
                if "c" in a: act.append(["c", R(a["c"][0]), R(a["c"][1])])
                if "to" in a: act.append(["to", R(a["to"][0]), R(a["to"][1])])
            mobs.append([m.nid, m.kind, R(m.x), R(m.y), m.dir, R(m.hp), R(m.maxhp), round(max(0, m.flash), 2),
                         m.anim, round(m.anim_t, 3), None if m.anim_p is None else round(m.anim_p, 3), act,
                         m.hands.net_pack() if getattr(m, "hands", None) else None])
        pls = []
        for p in s.players.values():
            atk = [p.atk["w"], p.atk["n"], round(p.atk["t"], 3)] if p.state == "attack" and p.atk else None
            cast = [p.skill_cast[0], round(p.skill_cast[1], 3), p.skill_cast[2]] if p.skill_cast else None
            pls.append({"id": p.pid, "n": p.name, "c": p.char_id, "x": R(p.x), "y": R(p.y), "h": p.h, "f": p.face, "st": p.state,
                        "an": p.anim, "at": round(p.anim_t, 3), "ap": None if p.anim_p is None else round(p.anim_p, 3),
                        "hp": R(p.hp), "mhp": p.maxhp, "mp": R(p.mana), "mmp": p.maxmana, "mf": round(max(0, p.mana_flash), 2),
                        "inv": round(max(0, p.inv), 2), "atk": atk, "aim": [R(p.aim[0]), R(p.aim[1])] if p.aim else None,
                        "sl": list(p.slots), "lw": p.last_weapon, "sc": cast,
                        "sh": [round(p.shield_time, 2), p.shield_face, R(p.shield_hp)],
                        "sk": list(p.skills), "si": p.skill_index, "cd": {k: round(v, 2) for k, v in p.skill_cooldowns.items() if v > 0},
                        "lv": p.level, "xp": p.xp, "xn": p.xp_next, "rv": round(p.revive, 2),
                        "tp": p.tp, "hc": p.hitc, "kb": [R(p.kb[0]), R(p.kb[1])], "gr": 1 if p.grab else 0})
        return {"t": "snap", "ht": round(time.monotonic(), 4), "room": r.id, "loop": g.camp.loop,
                "spawned": bool(r.spawned), "locked": r.locked, "cleared": r.cleared,
                "prog": {mid: [m.visited, m.cleared] for mid, m in g.camp.maps.items()},
                "done": g.done, "over": s.game_over, "pl": pls, "mobs": mobs,
                "corpses": [[c.kind, c.dir, c.rect.x, c.rect.y, c.rect.w, c.rect.h, round(c.t, 3)] for c in r.corpses],
                "projs": projs, "styles": styles, "drops": [[R(d.x), R(d.y), d.wid] for d in r.drops],
                "fx": [[k, R(x), R(y), R(d) if isinstance(d, (int, float)) else d, round(t, 3)] for k, x, y, d, t in g.fx.items]}

    _nid = 0
    def next_nid(s):
        s._nid += 1; return s._nid

    def update(s, dt):
        s.accept()
        for pid, c in list(s.conns.items()): s.process(pid, c)
        if s.phase == "game":
            s.step(dt)
            if s.conns:
                data = pack(s.snapshot())
                for c in s.conns.values(): c.send_raw(data, snapshot=True)
        s.track_local()

    def close(s):
        bye = pack({"t": "bye", "reason": "Хост завершил игру"})
        for c in list(s.conns.values()):
            c.send_raw(bye); c.close(flush=True)
        for c, _, _ in s.pending: c.close()
        s.conns.clear(); s.server.close()


def anchor_rect(p):
    """Клетка под ногами игрока p — туда ставим союзника."""
    return pg.Rect(int(p.cx - T / 2), int(p.y + p.h - T), T, T)


def place(p, rect, ladder, room, dx=0):
    """Поставить игрока p в точку появления rect (как Game.place, но для любого игрока; dx — сдвиг, чтобы не стоять друг в друге)."""
    if p.h != p.H0: p.y -= p.H0 - p.h; p.h = p.H0
    p.atk = None; p.grab = None; p.state = "ladder" if ladder and p.hp > 0 else "move"
    lim = lambda x: max(0, min(room.width_px - p.w, x))
    x = lim(rect.centerx - p.w / 2 + dx); p.y = rect.bottom - p.h; p.vx = p.vy = 0
    if dx and not free(room.g, pg.Rect(int(x), int(p.y), p.w, p.h)): x = lim(rect.centerx - p.w / 2)
    p.x = x; p.tp += 1   # клиент увидит новый tp и переставит своего героя сюда


# ======================================================================
#  Клиент
# ======================================================================
class NetCorpse(Corpse):
    def __init__(s, kind, d, direction, rect, t):
        s.kind, s.d, s.dir, s.rect, s.flies = kind, d, direction, rect, d.get("flies", False)
        s.t = t; s.dur = t + 1


class ClientSession(Session):
    """Клиент. Мир приходит снимками от хоста; чтобы картинка была плавной даже на Wi-Fi, где пакеты приходят пачками:
      * свой герой считается прямо здесь (как в одиночной игре) — отзывается на кнопки сразу;
        хост присылает только здоровье, ману, опыт, попадания (отброс) и перестановки (переход на карту, пропасть);
      * остальное (мобы, союзники, снаряды) показывается с небольшой задержкой и плавно между снимками.
        Задержка подстраивается под сеть: по кабелю ~25 мс, на «пачечном» Wi-Fi ~100 мс."""
    is_host = False
    MIN_DELAY, MAX_DELAY = .025, .3

    def __init__(s, g, host, port, name):
        super().__init__(g)
        s.addr = (host, port); s.name = clean_name(name); s.state = "connecting"; s.error = None
        s.conn = None; s.ready = False; s.events = []; s.mobs = {}; s.camp = None
        s.buf = deque(maxlen=90); s.latest = None; s.lat = deque(); s.delay = .06
        s.predicting = False; s.local_tp = None; s.local_hc = None
        s.scratch_projs = []; s.scratch_fx = FX()
        threading.Thread(target=s._connect, daemon=True).start()

    def _connect(s):
        try:
            sock = socket.create_connection(s.addr, timeout=4)
            conn = Conn(sock)
            conn.send({"t": "hello", "proto": PROTO, "sig": content_sig(), "name": s.name,
                       "char": SETTINGS.get("last_character", CHAR["id"])})
            s.conn = conn
        except OSError as e:
            s.error = describe_error(e)

    def address_line(s): return f"Подключено к {s.addr[0]}:{s.addr[1]}"

    def set_char(s, cid):
        SETTINGS["last_character"] = cid; s.g.save_settings()
        if s.conn: s.conn.send({"t": "char", "char": cid})

    def start(s): pass                    # начинает только хост
    def restart(s): pass
    def next_loop(s): pass

    def me(s): return s.players.get(s.my_id)

    def local_action(s, name):
        p = s.me()
        if p is None or p.hp <= 0: return
        s.events.append(name)
        if s.predicting and name in ("jump", "roll", "a1", "a2", "skill"): p.press(name)   # сразу и у себя

    def update(s, dt):
        g = s.g
        if s.state == "connecting" and s.error: g.net_leave(f"Не удалось подключиться к {s.addr[0]}:{s.addr[1]} — {s.error}", "connect"); return
        if not s.conn: return
        now = time.monotonic()
        for _ in range(500):
            try: msg = s.conn.inbox.get_nowait()
            except queue.Empty: break
            t = msg.get("t")
            if t == "snap":
                if s.phase == "game": s.on_snap(msg, now)
                continue
            if t == "welcome":
                s.my_id = msg.get("id"); s.state = "joined"; s.phase = msg.get("phase", "lobby")
                g.mp_status = ""
                if s.phase == "game": s.enter_game()
                else: char_menu.open_lobby(g)
            elif t == "reject": g.net_leave(msg.get("reason", "Хост отказал в подключении"), "connect"); return
            elif t == "lobby": s.lobby = [e for e in msg.get("players", []) if isinstance(e, dict)]
            elif t == "start": s.phase = "game"; s.enter_game()
            elif t == "bye": g.net_leave(msg.get("reason", "Хост завершил игру")); return
            elif t == "_closed":
                g.net_leave("Соединение с хостом потеряно" if s.state == "joined" else "Хост закрыл соединение"); return
        if s.phase == "game" and s.latest is not None:
            try: s.render(now, dt)
            except (KeyError, IndexError, TypeError, ValueError) as e:
                print("[сеть] не удалось применить снимок:", e)
        if s.in_game:
            s.predict(dt)
            aim = local_aim(g); p = s.me()
            pose = None
            if p is not None and p.hp > 0 and s.predicting:
                pose = [round(p.x, 2), round(p.y, 2), round(p.vx, 1), round(p.vy, 1), p.h, p.face, s.local_tp]
            s.conn.send({"t": "in", "k": local_bits(g), "aim": [round(aim[0], 1), round(aim[1], 1)] if aim else None,
                         "mb": list(local_mb(g)), "ev": s.events, "pose": pose})
            s.events = []
        s.track_local()

    def enter_game(s):
        g = s.g
        me = next((e for e in s.lobby if e.get("id") == s.my_id), None)
        if me and me.get("char"): apply_character(me["char"])
        g.menu_mode = None; g.level_menu = False; g.show_world = False
        s.ready = False; s.camp = None; s.mobs = {}; s.players = {}
        s.buf.clear(); s.latest = None; s.lat.clear(); s.predicting = False; s.local_tp = s.local_hc = None
        g.fx = FX(); g.projs = []

    # ---------- приём снимков и задержка показа ----------
    def on_snap(s, sn, now):
        ht = _num(sn.get("ht"), now)
        if s.latest is not None and (sn.get("room") != s.latest.get("room") or sn.get("loop") != s.latest.get("loop")):
            s.buf.clear()   # другая карта — старые снимки не смешиваем с новыми
        s.buf.append(sn); s.latest = sn
        s.lat.append((now, now - ht))
        while s.lat and now - s.lat[0][0] > 3: s.lat.popleft()

    def render_time(s, now, dt):
        """Момент времени хоста, который показываем: «сейчас» минус задержка, покрывающая неровный приход пакетов."""
        samples = [v for _, v in s.lat]
        offset = min(samples)
        late = sorted(v - offset for v in samples)
        target = late[int(.95 * (len(late) - 1))] + .012
        target = max(s.MIN_DELAY, min(s.MAX_DELAY, target))
        k = min(1.0, dt * (4.0 if target > s.delay else .6))   # растём быстро, уменьшаемся плавно
        s.delay += (target - s.delay) * k
        return now - offset - s.delay

    def pick(s, rt):
        """Два снимка вокруг момента rt и доля между ними."""
        buf = s.buf
        if len(buf) == 1 or rt <= buf[0]["ht"]: return buf[0], None, 0.0
        for i in range(len(buf) - 1, -1, -1):
            if buf[i]["ht"] <= rt:
                a = buf[i]
                if i + 1 < len(buf):
                    b = buf[i + 1]; span = max(1e-4, b["ht"] - a["ht"])
                    return a, b, min(1.0, (rt - a["ht"]) / span)
                return a, None, 0.0
        return buf[0], None, 0.0

    def render(s, now, dt):
        g, sn = s.g, s.latest
        s.apply_world(sn)
        a, b, k = s.pick(s.render_time(now, dt))
        ahead = max(0.0, min(.1, (b["ht"] - a["ht"]) * k if b else 0.0))   # сколько прошло после снимка a
        s.apply_players(a, b, k, ahead)
        s.apply_mobs(g.room, a, b, k, ahead, dt)
        corpses = []
        for kind, d, x, y, w, h, t in a.get("corpses", []):
            if kind in CFG["mobs"]: corpses.append(NetCorpse(kind, normalize(CFG["mobs"][kind]), d, pg.Rect(x, y, w, h), t + ahead))
        g.room.corpses = corpses
        styles = a.get("styles", [])
        bq = {row[0]: row for row in b.get("projs", [])} if b else {}
        projs = []
        for nid, x, y, vx, vy, t, si in a.get("projs", []):
            st = styles[si] if 0 <= si < len(styles) else {}
            nb = bq.get(nid)
            if nb and abs(nb[1] - x) < 200 and abs(nb[2] - y) < 200: x, y = x + (nb[1] - x) * k, y + (nb[2] - y) * k
            else: x, y = x + vx * ahead, y + vy * ahead
            q = Proj(x, y, vx, vy, st, 0, True); q.t = t + ahead; projs.append(q)
        g.projs = projs
        g.fx.items = [[it[0], it[1], it[2], it[3], it[4] - ahead] for it in a.get("fx", [])
                      if isinstance(it, list) and len(it) == 5 and it[4] - ahead > 0]
        me = s.me() or next(iter(s.players.values()), None)
        if me is not None:
            g.pl = me
            if me.char_id and CHAR["id"] != me.char_id: apply_character(me.char_id)
            s.ready = True

    def apply_world(s, sn):
        """Карта, двери, предметы и итоги забега — по самому свежему снимку."""
        g = s.g
        if s.camp is None or s.camp.loop != sn["loop"]:
            s.camp = Campaign(sn["loop"]); s.mobs = {}
        g.camp = s.camp
        for mid, (vis, clr) in sn.get("prog", {}).items():
            if mid in CFG["map_defs"]:
                m = s.camp.get(mid); m.visited, m.cleared = bool(vis), bool(clr)
        if sn["room"] not in CFG["map_defs"]: return
        r = s.camp.get(sn["room"])
        if g.room is not r: g.room = r; s.mobs = {}
        if r.locked != bool(sn["locked"]): r.set_lock(bool(sn["locked"]))
        r.cleared = bool(sn["cleared"])
        r.spawned = bool(sn.get("spawned", True))
        r.drops = [Drop(x, y, wid) for x, y, wid in sn.get("drops", []) if wid in CFG["weapons_base"]]
        g.done = bool(sn.get("done")); s.game_over = bool(sn.get("over"))

    # ---------- игроки ----------
    def player_obj(s, pid, cid):
        p = s.players.get(pid)
        if p is None or p.char_id != cid:
            with use_char(cid):
                p = s.g.Player()
            p.pid = pid; s.players[pid] = p
        return p

    def apply_players(s, a, b, k, ahead):
        latest = {ps["id"]: ps for ps in s.latest.get("pl", [])}
        rows_a = {ps["id"]: ps for ps in a.get("pl", [])}
        rows_b = {ps["id"]: ps for ps in b.get("pl", [])} if b else {}
        for pid in list(s.players):
            if pid not in latest: del s.players[pid]
        for pid, lp in latest.items():
            p = s.player_obj(pid, lp.get("c"))
            if pid == s.my_id: s.apply_self(p, lp); continue
            ps = rows_a.get(pid, lp); nb = rows_b.get(pid)
            s.apply_pose(p, ps)
            s.apply_stats(p, ps)
            p.aim = tuple(ps["aim"]) if ps.get("aim") else None
            if nb and abs(nb["x"] - ps["x"]) < 150 and abs(nb["y"] - ps["y"]) < 150:
                p.x += (nb["x"] - ps["x"]) * k; p.y += (nb["y"] - ps["y"]) * k
                if nb["an"] == ps["an"]: p.anim_t += (nb["at"] - ps["at"]) * k
                else: p.anim_t += ahead
            else: p.anim_t += ahead

    def apply_pose(s, p, ps):
        p.name = ps.get("n", "")
        p.x, p.y, p.h, p.face, p.state = ps["x"], ps["y"], ps["h"], ps["f"], ps["st"]
        p.anim, p.anim_t, p.anim_p = ps["an"], ps["at"], ps["ap"]
        p.inv = ps["inv"]
        p.skill_cast = tuple(ps["sc"]) if ps.get("sc") else None
        p.atk = None
        if ps.get("atk"):
            wid, n, t = ps["atk"]
            with use_char(ps.get("c")):
                steps = CFG["weapons"].get(wid, {}).get("combo")
                if steps:
                    st = steps[n % len(steps)]
                    p.atk = dict(w=wid, n=n, step=st, t=t, wu=st["windup"], ac=st["active"], rec=st["recovery"], fired=True, hit=set())

    def apply_stats(s, p, ps):
        """Что всегда решает хост: здоровье, мана, оружие, навыки, опыт, щит."""
        p.hp, p.maxhp, p.mana, p.maxmana = ps["hp"], ps["mhp"], ps["mp"], ps["mmp"]
        p.mana_flash = max(p.mana_flash, ps["mf"]) if p.pid == s.my_id else ps["mf"]
        p.revive = ps.get("rv", 0); p.downed = p.hp <= 0
        p.slots = list(ps["sl"])
        if p.pid != s.my_id or not s.predicting: p.last_weapon = ps["lw"]
        p.shield_time, p.shield_face, p.shield_hp = ps["sh"]
        p.skills, p.skill_index = list(ps["sk"]), ps["si"]
        host_cd = {k: float(v) for k, v in ps.get("cd", {}).items()}
        if p.pid == s.my_id and s.predicting:   # только что применённый навык не «оживает», пока хост не подтвердил
            host_cd = {k: max(host_cd.get(k, 0.0), p.skill_cooldowns.get(k, 0.0)) for k in set(host_cd) | set(p.skill_cooldowns)}
        p.skill_cooldowns = host_cd
        p.level, p.xp, p.xp_next = ps["lv"], ps["xp"], ps["xn"]

    def apply_self(s, p, ps):
        alive = ps["hp"] > 0
        if not alive or ps.get("gr"):   # павший или схваченный рукой босса: показываем как у хоста, ничего не предсказываем
            s.predicting = False
            s.apply_pose(p, ps); s.apply_stats(p, ps); p.aim = None
            s.local_hc = ps.get("hc", 0); return
        if not s.predicting or ps.get("tp") != s.local_tp:
            # первое появление, переход на другую карту, пропасть, воскрешение — встаём туда, куда поставил хост
            s.apply_pose(p, ps)
            p.vx = p.vy = 0.0; p.atk = None; p.skill_cast = None; p.stun = 0
            if p.state not in ("move", "ladder"): p.state = "move"
            if p.h != p.H0: p.y -= p.H0 - p.h; p.h = p.H0
            for key_ in p.buf: p.buf[key_] = 0
            s.local_tp = ps.get("tp"); s.predicting = True
            s.local_hc = ps.get("hc", 0)
        elif ps.get("hc", 0) != s.local_hc:
            # хост засчитал попадание — отбрасываем своего героя так же, как в одиночной игре
            s.local_hc = ps.get("hc", 0)
            p.vx, p.vy = ps.get("kb", [0, 0]); p.stun = .18
            with use_char(p.char_id): p.inv = max(p.inv, CFG["player"]["hurt_inv"])
            if p.state in ("attack", "ladder"): p.state = "move"; p.atk = None
        s.apply_stats(p, ps)

    def predict(s, dt):
        """Свой герой: та же физика и атаки, что в одиночной игре, по своим клавишам — без ожидания хоста."""
        p, g = s.me(), s.g
        if p is None or p.hp <= 0 or not s.predicting: return
        p.aim = local_aim(g)
        mb = local_mb(g)
        if mb[0]: p.press("a1")
        if mb[1]: p.press("a2")
        # мобов не передаём: урон считает хост. Свои пули и надписи здесь не нужны — их пришлёт хост.
        p.update(dt, NetKeys(local_bits(g)), g.room.g, [], s.scratch_projs, s.scratch_fx); p.update_anim(dt)
        s.scratch_projs.clear(); s.scratch_fx.items.clear()

    # ---------- мобы ----------
    def apply_mobs(s, r, a, b, k, ahead, dt=0.0):
        rows_b = {row[0]: row for row in b.get("mobs", [])} if b else {}
        out, seen = [], set()
        for nid, kind, x, y, d, hp, mhp, fl, an, at, ap, act, *extra in a.get("mobs", []):
            if kind not in CFG["mobs"]: continue
            m = s.mobs.get(nid)
            if m is None or m.kind != kind:
                m = s.mobs[nid] = Mob(kind, x, y, 1.0, r)      # r — комната: от неё Моргарт берёт раскладку рук
            seen.add(nid)
            nb = rows_b.get(nid)
            if nb and abs(nb[2] - x) < 150 and abs(nb[3] - y) < 150:
                x, y = x + (nb[2] - x) * k, y + (nb[3] - y) * k
                at = at + (nb[9] - at) * k if nb[8] == an else at + ahead
            else: at += ahead
            m.x, m.y, m.dir, m.hp, m.maxhp, m.flash = x, y, d, hp, mhp, fl
            m.anim, m.anim_t, m.anim_p = an, at, ap
            m.t += dt      # у клиентского моба нет update(): без этого «часы» Моргарта стоят на 0 и босс рисуется полностью прозрачным
            if getattr(m, "hands", None) and extra and extra[0]:
                nbh = nb[12] if nb and len(nb) > 12 else None
                m.hands.net_apply(extra[0], nbh, k, ahead)
                m.alone = not m.hands.alive_count()
            m.act = None
            if act:
                i, ph, t = act[0], act[1], act[2]
                if 0 <= i < len(m.attacks) and m.attacks[i].get("type") in ATTACKS:
                    at_ = m.attacks[i]
                    m.act = {"a": at_, "h": ATTACKS[at_["type"]], "i": i, "phase": ph, "t": t + ahead, "hit": False}
                    for extra in act[3:]: m.act[extra[0]] = (extra[1], extra[2])
            out.append(m)
        s.mobs = {key_: v for key_, v in s.mobs.items() if key_ in seen}
        r.mobs = out

    def close(s):
        if s.conn:
            s.conn.send({"t": "bye"}); s.conn.close(flush=True)


def describe_error(e):
    if isinstance(e, socket.timeout): return "хост не отвечает (проверьте IP и брандмауэр)"
    if isinstance(e, ConnectionRefusedError): return "на этом адресе нет игры (хост не создан или другой порт)"
    if isinstance(e, socket.gaierror): return "неверный адрес"
    return str(e) or e.__class__.__name__


# ======================================================================
#  Отрисовка сетевой игры
# ======================================================================
def draw_players(g, v):
    """Все игроки: свой — поверх остальных; над союзниками — имя; павшие — полупрозрачные, с полоской воскрешения."""
    net, me = g.net, g.pl
    tick = int(pg.time.get_ticks() / 60) % 2
    order = [p for p in net.player_list() if p is not me] + ([me] if me in net.player_list() else [])
    for p in order:
        if p.hp <= 0: draw_downed(g, v, p); continue
        if p.inv <= 0 or tick: p.draw(v)
        if p is not me:
            col = net.color_of(p.pid); t = g.small.render(p.name, True, col)
            r = p.rect; x, y = r.centerx - t.get_width() // 2, r.top - 30
            v.blit(g.small.render(p.name, True, (0, 0, 0)), (x + 1, y + 1)); v.blit(t, (x, y))
            pg.draw.rect(v, (50, 20, 20), (r.centerx - 16, y + 14, 32, 3))
            pg.draw.rect(v, (220, 60, 60), (r.centerx - 16, y + 14, int(32 * max(0, p.hp) / max(1, p.maxhp)), 3))


def draw_downed(g, v, p):
    r = p.rect
    with use_char(p.char_id):
        pc = CFG["player"]
        dw, dh = pc.get("draws", {}).get("hurt", pc.get("draw", [p.w, p.H0]))
        dw, dh = max(1, int(dw * p.model_scale)), max(1, int(dh * p.model_scale))
        img = sprite(mob_frame(f"player:{p.char_id}", pc, ["hurt"], 0.0, None, folder=pc.get("folder", "player")), dw, dh, p.face < 0)
    if img:
        img = pg.transform.rotate(img, 90 if p.face < 0 else -90); img.set_alpha(140)   # лежит
        v.blit(img, img.get_rect(midbottom=(r.centerx, r.bottom)))
    else:
        pg.draw.rect(v, (120, 110, 130), (r.centerx - r.h // 2, r.bottom - r.w // 2, r.h, r.w // 2), border_radius=4)
    col = g.net.color_of(p.pid)
    t = g.small.render(f"{p.name}: встаньте рядом, чтобы поднять", True, col)
    v.blit(t, (r.centerx - t.get_width() // 2, r.bottom - 44))
    k = max(0.0, min(1.0, p.revive / REVIVE_TIME))
    pg.draw.rect(v, (30, 30, 40), (r.centerx - 30, r.bottom - 28, 60, 6))
    pg.draw.rect(v, (120, 235, 140), (r.centerx - 30, r.bottom - 28, int(60 * k), 6))


def draw_overlay(g):
    """Поверх HUD: союзники (слева сверху), плашка уровня, сообщения о смерти и конце круга."""
    net, scr, me = g.net, g.scr, g.pl
    y = 34
    for p in net.player_list():
        if p is me: continue
        col = net.color_of(p.pid)
        name = ("✝ " if p.hp <= 0 else "") + p.name
        g.txt(name, 12, y, col if p.hp > 0 else (200, 110, 110), g.small)
        pg.draw.rect(scr, (40, 20, 24), (12, y + 15, 90, 5))
        pg.draw.rect(scr, (220, 60, 60), (12, y + 15, int(90 * max(0, p.hp) / max(1, p.maxhp)), 5))
        y += 26
    role = (f"ХОСТ · {net.ips[0]}:{net.port}" if net.is_host else f"КЛИЕНТ · {net.addr[0]}") + f" · игроков: {len(net.player_list())}"
    t = g.small.render(role, True, (170, 200, 230)); scr.blit(t, (W - t.get_width() - 10, 24))
    if net.banner and pg.time.get_ticks() < net.banner[1]:
        t = g.font.render(net.banner[0], True, (255, 225, 140))
        bg = pg.Surface((t.get_width() + 28, t.get_height() + 12), pg.SRCALPHA); bg.fill((10, 10, 20, 190))
        scr.blit(bg, bg.get_rect(center=(W // 2, 64))); scr.blit(t, t.get_rect(center=(W // 2, 64)))
    def center(text, y, col, font):
        t = font.render(text, True, col); scr.blit(font.render(text, True, (0, 0, 0)), t.get_rect(center=(W // 2 + 2, y + 2))); scr.blit(t, t.get_rect(center=(W // 2, y)))
    if net.game_over:
        center("ВСЕ ПОГИБЛИ", 190, (255, 90, 90), g.big)
        center("R — новый забег для всех" if net.is_host else "Ждём, пока хост начнёт новый забег", 236, (255, 200, 190), g.font)
    elif me.hp <= 0:
        center("ТЫ ПАЛ", 190, (255, 110, 110), g.big)
        center("Союзник поднимет тебя, если постоит рядом. Зачистка карты тоже поднимает.", 236, (255, 210, 200), g.font)
    elif g.done:
        center("ВСЕ КАРТЫ ПРОЙДЕНЫ", 190, (120, 255, 150), g.big)
        center("Enter — ещё круг для всех" if net.is_host else "Ждём, пока хост начнёт следующий круг", 236, (200, 255, 210), g.font)


# ======================================================================
#  Меню «Мультиплеер» и «Подключиться»
# ======================================================================
MP_RECTS = {"name": (330, 150, 300, 38), "host": (330, 212, 300, 44), "connect": (330, 266, 300, 44), "back": (380, 332, 200, 38)}
CN_RECTS = {"ip": (280, 122, 400, 40), "go": (280, 174, 400, 44), "back": (380, 440, 200, 36)}
HOST_ROW = (280, 262, 400, 32)


def open_menu(g, message=""):
    g.menu_mode = "mp"; g.mp_focus = None; g.mp_status = message
    _text_input(True)


def open_connect(g):
    g.menu_mode = "connect"; g.mp_status = ""
    if g.mp_finder is None: g.mp_finder = Finder()
    _text_input(True)


def _text_input(on):
    try:
        (pg.key.start_text_input if on else pg.key.stop_text_input)()
    except (AttributeError, pg.error): pass


def housekeeping(g):
    """Закрыть поиск хостов, когда экран подключения больше не открыт."""
    if g.mp_finder is not None and g.menu_mode != "connect":
        g.mp_finder.close(); g.mp_finder = None


def save_name(g):
    g.mp_name = clean_name(g.mp_name, default_name())
    SETTINGS["player_name"] = g.mp_name; g.save_settings()


def host_game(g):
    save_name(g)
    try:
        g.net = HostSession(g, g.mp_name)
    except OSError as e:
        g.net = None
        g.mp_status = f"Не удалось создать игру на порту {PORT}: {e}. Закройте другую копию игры или программу на этом порту."
        return
    char_menu.open_lobby(g)


def connect(g, text=None):
    if g.net: return   # уже подключаемся
    text = g.mp_ip if text is None else text
    addr, err = parse_address(text)
    if err: g.mp_status = err; return
    g.mp_ip = text.strip(); SETTINGS["mp_last_ip"] = g.mp_ip; g.save_settings()
    save_name(g)
    g.net = ClientSession(g, addr[0], addr[1], g.mp_name)
    g.mp_status = f"Подключение к {addr[0]}:{addr[1]}…"


def cancel_connect(g):
    if g.net and not g.net.is_host: g.net.close()
    g.net = None


def _paste():
    for fn in ("get_text",):
        try:
            txt = getattr(pg.scrap, fn)()
            if txt: return txt
        except Exception: pass
    try:
        if not pg.scrap.get_init(): pg.scrap.init()
        raw = pg.scrap.get("text/plain;charset=utf-8") or pg.scrap.get(pg.SCRAP_TEXT)
        if raw: return raw.decode("utf-8", "ignore").strip("\x00")
    except Exception: pass
    return ""


def menu_key(g, k):
    ctrl = pg.key.get_mods() & pg.KMOD_CTRL
    if g.menu_mode == "mp":
        if g.mp_focus == "name":
            if k in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_ESCAPE, pg.K_TAB): g.mp_focus = None; save_name(g)
            elif k == pg.K_BACKSPACE: g.mp_name = g.mp_name[:-1]
            elif k == pg.K_v and ctrl: g.mp_name = clean_name(g.mp_name + _paste(), "")[:16]
            return
        if k == pg.K_ESCAPE: g.menu_mode = "start"; g.mp_status = ""
        elif k in (pg.K_RETURN, pg.K_KP_ENTER): open_connect(g)
        elif k == pg.K_F11: pg.display.toggle_fullscreen()
    elif g.menu_mode == "connect":
        if k == pg.K_ESCAPE:
            cancel_connect(g); open_menu(g)
        elif k in (pg.K_RETURN, pg.K_KP_ENTER): connect(g)
        elif k == pg.K_BACKSPACE and not g.net: g.mp_ip = g.mp_ip[:-1]
        elif k == pg.K_v and ctrl and not g.net: g.mp_ip = _ip_chars(g.mp_ip + _paste())[:40]
        elif k == pg.K_F11: pg.display.toggle_fullscreen()


def _ip_chars(t): return "".join(ch for ch in t if ch.isalnum() or ch in ".:-_[]")


def menu_event(g, e):
    if e.type == pg.TEXTINPUT:
        if g.menu_mode == "mp" and g.mp_focus == "name":
            g.mp_name = (g.mp_name + "".join(ch for ch in e.text if ch.isprintable()))[:16]
        elif g.menu_mode == "connect" and not g.net:
            g.mp_ip = _ip_chars(g.mp_ip + e.text)[:40]
        return
    if e.type != pg.MOUSEBUTTONDOWN or e.button != 1: return
    hit = lambda key, rects: pg.Rect(rects[key]).collidepoint(e.pos)
    if g.menu_mode == "mp":
        if hit("name", MP_RECTS): g.mp_focus = "name"; return
        if g.mp_focus == "name": g.mp_focus = None; save_name(g)
        if hit("host", MP_RECTS): host_game(g)
        elif hit("connect", MP_RECTS): open_connect(g)
        elif hit("back", MP_RECTS): g.menu_mode = "start"; g.mp_status = ""
    elif g.menu_mode == "connect":
        if hit("go", CN_RECTS): connect(g)
        elif hit("back", CN_RECTS): cancel_connect(g); open_menu(g)
        elif g.mp_finder and not g.net:
            for i, (key, info) in enumerate(g.mp_finder.hosts()[:4]):
                x, y, w, h = HOST_ROW
                if pg.Rect(x, y + i * 38, w, h).collidepoint(e.pos):
                    g.mp_ip = key; connect(g); return


def _button(g, rect, label, active=True, focus=False):
    r = pg.Rect(rect); hov = active and r.collidepoint(pg.mouse.get_pos())
    img = g.menu_button_selected if (hov or focus) else g.menu_button
    if img: g.scr.blit(pg.transform.smoothscale(img, r.size), r.topleft)
    pg.draw.rect(g.scr, (92, 76, 130) if hov else (34, 32, 50), r, border_radius=8)
    pg.draw.rect(g.scr, (200, 180, 255) if hov or focus else (110, 100, 140), r, 2, border_radius=8)
    t = g.font.render(label, True, (250, 248, 255) if active else (150, 150, 170)); g.scr.blit(t, t.get_rect(center=r.center))


def _field(g, rect, value, focus, placeholder=""):
    r = pg.Rect(rect)
    pg.draw.rect(g.scr, (18, 18, 28), r, border_radius=6)
    pg.draw.rect(g.scr, (255, 214, 120) if focus else (110, 100, 140), r, 2, border_radius=6)
    shown = value or placeholder
    t = g.font.render(shown, True, (245, 245, 255) if value else (120, 120, 140))
    g.scr.blit(t, (r.x + 10, r.centery - t.get_height() // 2))
    if focus and (pg.time.get_ticks() // 500) % 2:
        x = r.x + 10 + (g.font.size(value)[0] if value else 0) + 1
        pg.draw.line(g.scr, (255, 255, 255), (x, r.y + 9), (x, r.bottom - 9), 2)


def _backdrop(g, title):
    if g.menu_background: g.scr.blit(pg.transform.smoothscale(g.menu_background, (W, VIEW_H)), (0, 0))
    else: g.scr.fill((8, 8, 17))
    veil = pg.Surface((W, VIEW_H), pg.SRCALPHA); veil.fill((6, 6, 14, 175)); g.scr.blit(veil, (0, 0))
    t = g.big.render(title, True, (255, 220, 130)); g.scr.blit(t, t.get_rect(center=(W // 2, 62)))


def _center(g, text, y, col, font=None):
    font = font or g.small
    t = font.render(text, True, col); g.scr.blit(t, t.get_rect(center=(W // 2, y)))


def _status(g, y):
    if not g.mp_status: return
    words, line, lines = g.mp_status.split(), "", []
    for w_ in words:
        test = (line + " " + w_).strip()
        if g.small.size(test)[0] > 640 and line: lines.append(line); line = w_
        else: line = test
    lines.append(line)
    for i, ln in enumerate(lines[:3]): _center(g, ln, y + i * 16, (255, 170, 120))


def draw_menu(g):
    if g.menu_mode == "mp": draw_mp(g)
    else: draw_connect(g)


def draw_mp(g):
    _backdrop(g, "МУЛЬТИПЛЕЕР")
    x, y, w, h = MP_RECTS["name"]
    g.txt("Ваше имя в игре:", x, y - 20, (200, 200, 220), g.small)
    _field(g, MP_RECTS["name"], g.mp_name, g.mp_focus == "name", "нажмите, чтобы ввести имя")
    _button(g, MP_RECTS["host"], "СТАТЬ ХОСТОМ")
    _button(g, MP_RECTS["connect"], "ПОДКЛЮЧИТЬСЯ")
    _button(g, MP_RECTS["back"], "НАЗАД")
    _status(g, 392)
    _center(g, "Хост создаёт лобби, остальные подключаются по его IP. Все — в одной сети (один Wi-Fi или роутер).", VIEW_H - 46, (175, 180, 205))
    _center(g, f"Порты: TCP {PORT} — игра, UDP {DISCOVERY_PORT} — поиск игр. Если не находит — разрешите игру в брандмауэре.", VIEW_H - 28, (150, 155, 180))


def draw_connect(g):
    _backdrop(g, "ПОДКЛЮЧЕНИЕ")
    if g.mp_finder: g.mp_finder.update()
    x, y, w, h = CN_RECTS["ip"]
    g.txt("IP-адрес хоста (например 192.168.1.5 или 192.168.1.5:5555):", x, y - 20, (200, 200, 220), g.small)
    busy = bool(g.net)
    _field(g, CN_RECTS["ip"], g.mp_ip, not busy, "192.168.…")
    _button(g, CN_RECTS["go"], "ПОДКЛЮЧЕНИЕ…" if busy else "ПОДКЛЮЧИТЬСЯ", not busy)
    hx, hy, hw, hh = HOST_ROW
    g.txt("Игры в локальной сети (нажмите, чтобы подключиться):", hx, hy - 22, (200, 200, 220), g.small)
    hosts = g.mp_finder.hosts()[:4] if g.mp_finder else []
    if not hosts:
        dots = "." * (1 + (pg.time.get_ticks() // 400) % 3)
        g.txt("поиск" + dots, hx + 10, hy + 6, (140, 140, 165), g.small)
    mouse = pg.mouse.get_pos()
    for i, (key, info) in enumerate(hosts):
        r = pg.Rect(hx, hy + i * 38, hw, hh); hov = r.collidepoint(mouse) and not busy
        pg.draw.rect(g.scr, (60, 52, 92) if hov else (26, 25, 40), r, border_radius=6)
        pg.draw.rect(g.scr, (160, 150, 210) if hov else (80, 76, 110), r, 1, border_radius=6)
        phase = "в лобби" if info.get("phase") == "lobby" else "идёт забег"
        g.txt(f"{info.get('name', '?')}", r.x + 10, r.y + 7, (255, 230, 150), g.small)
        t = g.small.render(f"{key} · {info.get('players', '?')}/{info.get('max', MAX_PLAYERS)} · {phase}", True, (200, 205, 225))
        g.scr.blit(t, (r.right - t.get_width() - 10, r.y + 8))
    _button(g, CN_RECTS["back"], "НАЗАД")
    _status(g, 418 - 16 * (1 if len(g.mp_status) > 90 else 0))
