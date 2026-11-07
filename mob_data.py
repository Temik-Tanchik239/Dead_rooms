"""Данные и логика редактора мобов (вкладка «Мобы» в map_editor.py). Здесь нет ни tkinter, ни pygame — модуль можно
тестировать отдельно. Интерфейс — mob_editor.py, окно с мобом — mob_preview.py.

Что тут есть:
  · описания полей (F) для форм: характеристики моба, параметры каждого вида движения и каждого вида атаки
    (названия, подсказки и значения по умолчанию взяты из movement.py / attacks.py / mob.py);
  · чтение и запись data/mobs.json (формат файла сохраняется один в один — без правок diff пустой);
  · атаки: шаблоны, смена вида, названия фаз; анимации: список, источник кадров, управление PNG-файлами;
  · проверки (validate) и поиск упоминаний моба в картах (references).
"""
import copy, json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"


# ---------------------------------------------------------------- описание полей форм
class F:
    """Поле формы. kind: num | int | text | bool | choice | vec2 | rgb | points. Пустое поле = ключ не пишется (действует
    значение по умолчанию из игры, оно показано серым в hint). Ключ может быть составным: "light.radius"."""
    def __init__(s, key, label, kind="num", hint="", help="", choices=()):
        s.key, s.label, s.kind, s.hint, s.help, s.choices = key, label, kind, hint, help, tuple(choices)


STAT_GROUPS = [
    ("Характеристики", [
        F("name", "Название", "text", "", "Имя моба (показывается в игре и в списках)."),
        F("hp", "Здоровье", "num", "", "Сколько урона выдерживает (умножается на сложность карты)."),
        F("xp", "Опыт за убийство", "int", "0", "Сколько опыта получает игрок."),
        F("speed", "Скорость", "num", "80", "Базовая скорость (px/с). В параметрах движения можно задать свою."),
        F("mass", "Масса", "num", "1", "Чем больше, тем слабее моба отбрасывает от ударов."),
        F("contact", "Урон касанием", "num", "0", "Урон игроку, если коснуться моба."),
        F("weight", "Шанс появления", "num", "1", "Вес при случайном выборе моба для карты (если на карте нет mob_pool)."),
        F("dmg_scale", "Множитель урона", "num", "1", "Умножает урон всех его атак."),
    ]),
    ("Поведение", [
        F("flies", "Летает", "bool", "нет", "Летающий: без гравитации, висит в воздухе, рисуется по центру хитбокса."),
        F("armor", "Броня (удары не сбивают)", "bool", "нет", "Удары игрока не прерывают атаки и не оглушают."),
        F("stun", "Оглушение от удара, с", "num", "0.25", "Сколько секунд моб стоит оглушённым после удара."),
        F("sight", "Обзор по X, px", "num", "340", "С какого расстояния замечает игрока (если не задано в движении)."),
        F("sight_y", "Обзор по Y, px", "num", "140", "Допустимая разница по высоте при обнаружении."),
        F("attack_gap", "Пауза между атаками, с", "num", "0.3", "Сколько отдыхает после любой атаки."),
        F("blink", "Мигать на замахе", "bool", "да", "Моб мигает белым во время замаха атаки."),
        F("gravity", "Гравитация", "num", "1800", "Сила тяжести для этого моба."),
        F("jump", "Скорость прыжка", "num", "0", "Прыжок через стенку/яму при ходьбе (0 — авто, см. auto_jump)."),
        F("auto_jump", "Автопрыжок", "num", "470", "Скорость прыжка, если jump не задан."),
    ]),
    ("Свет вокруг моба", [
        F("light.radius", "Радиус, px", "num", "", "Радиус свечения. Пусто — моб не светится."),
        F("light.intensity", "Яркость 0..1", "num", "", "Сила свечения."),
        F("light.color", "Цвет", "rgb", "", "Цвет свечения."),
    ]),
]

MOVE_COMMON = [
    F("speed", "Скорость", "num", "из «Основное»", "Скорость в этом режиме движения (px/с)."),
    F("accel", "Ускорение", "num", "", "Как быстро набирает и меняет скорость."),
]
MOVES = {
    "chase": ("Преследование", "Увидел игрока — идёт/летит прямо на него и больше не отстаёт. До агра бродит (земной) или парит (летун).", [
        F("sight", "Обзор по X, px", "num", "340", "Дальность, с которой замечает игрока."),
        F("sight_y", "Обзор по Y, px", "num", "140", "Допустимая разница по высоте."),
        F("jump", "Скорость прыжка", "num", "0", "Запрыгивать на стенку в 1 блок (0 — авто)."),
        F("drop", "Спрыгивать с края", "bool", "да", "Прыгать вниз к игроку, если он ниже."),
        F("patrol", "Бродить до агра", "bool", "да", "Ходить туда-сюда, пока не заметил игрока."),
        F("offset_y", "Смещение цели по Y", "num", "-10", "Летуны целятся чуть выше (минус) или ниже центра игрока."),
    ]),
    "keep_distance": ("Держать дистанцию", "Подходит, если далеко, и отходит, если близко; всегда смотрит на игрока. Земные не шагают в пропасть.", [
        F("distance", "Желаемая дистанция, px", "num", "220", "На каком расстоянии от игрока держится."),
        F("band", "Допуск ±, px", "num", "50", "Пока дистанция в этих пределах — стоит на месте."),
        F("height", "Высота над игроком (летуны)", "num", "-70", "Минус = выше игрока."),
        F("sight", "Обзор по X, px", "num", "340", "Дальность, с которой замечает игрока."),
        F("patrol", "Бродить до агра", "bool", "да", "Ходить туда-сюда, пока не заметил игрока."),
        F("jump", "Скорость прыжка", "num", "0", "Прыжок через препятствия (0 — авто)."),
    ]),
    "loop": ("Полёт по циклу", "Летает по замкнутой траектории вокруг точки появления (или вокруг игрока) и на игрока не реагирует.", [
        F("shape", "Форма", "choice", "circle", "circle — круг, eight — восьмёрка, line — туда-обратно, path — свои точки.",
          ("circle", "eight", "line", "path")),
        F("radius", "Радиус [x, y], px", "vec2", "", "Размеры траектории."),
        F("period", "Секунд на круг", "num", "4", "За сколько проходит траекторию."),
        F("reverse", "В обратную сторону", "bool", "нет", "Менять направление облёта."),
        F("anchor", "Вокруг чего", "choice", "точки появления", "player — кружить вокруг игрока.", ("player",)),
        F("points", "Точки path (dx dy в строке)", "points", "", "Для формы path: смещения от точки появления."),
    ]),
    "stand": ("Стоять на месте", "Стоит на месте (летун висит) и поворачивается к игроку.", []),
}

ATTACK_COMMON = [
    F("id", "ID (для комбо)", "text", "", "Имя атаки: на него можно сослаться из поля «Следующая»."),
    F("windup", "Замах, с", "num", "0.4", "Фаза замаха: моб мигает, игрок может увернуться."),
    F("active", "Удар (длительность), с", "num", "0.12", "Фаза удара, когда зона поражает игрока."),
    F("recovery", "Отдых после, с", "num", "0.4", "Фаза после удара, когда моб беззащитен."),
    F("cooldown", "Перезарядка, с", "num", "1.5", "Через сколько снова можно применить эту атаку."),
    F("damage", "Урон", "num", "10", "Урон игроку."),
    F("knockback", "Отбрасывание", "num", "260", "Сила отбрасывания игрока."),
    F("range", "Дальность применения, px", "num", "", "С какого расстояния до игрока моб начинает эту атаку."),
    F("min_range", "Минимальная дальность, px", "num", "0", "Ближе этого атака не применяется."),
    F("range_y", "Допуск по высоте, px", "num", "", "Максимальная разница по высоте до игрока."),
    F("mobile", "Двигаться во время атаки", "bool", "нет", "Моб продолжает ходить по своему паттерну."),
    F("interrupt", "Удар сбивает замах", "bool", "да", "Нет — игрок не может прервать замах."),
    F("next", "Следующая атака (комбо)", "ref", "", "ID атаки, которая начнётся сразу после этой."),
]
ATTACK_TYPES = {
    "melee": ("Ближний удар", "Удар перед собой в зоне reach.", [
        F("reach", "Зона удара [ширина, высота], px", "vec2", "44, 30", "Прямоугольник перед мобом."),
        F("lunge", "Рывок вперёд, px/с", "num", "0", "Скорость рывка при ударе."),
    ]),
    "circle": ("Удар по кругу", "Круговая зона; на замахе игрок видит, куда прилетит.", [
        F("radius", "Радиус, px", "num", "80", "Радиус зоны поражения."),
        F("center", "Центр круга", "choice", "self", "self — вокруг себя, player — где стоял игрок в начале замаха.", ("self", "player")),
    ]),
    "shoot": ("Стрельба", "Выпускает снаряды из data/projectiles.json.", [
        F("projectile", "Снаряд", "proj", "bolt", "Тип снаряда."),
        F("aim", "Прицел", "choice", "player", "player — в игрока, forward — вперёд, ring — по кругу, angle — под углом.",
          ("player", "forward", "ring", "angle")),
        F("angle", "Угол, °", "num", "0", "Для aim=angle/ring: 0 — вперёд, -90 — вверх."),
        F("count", "Снарядов в залпе", "int", "1", "Сколько снарядов вылетает разом."),
        F("spread", "Разброс веера, °", "num", "0", "Угол между снарядами веера."),
        F("burst", "Залпов в очереди", "int", "1", "Сколько залпов подряд."),
        F("burst_gap", "Пауза между залпами, с", "num", "0.15", "Время между залпами очереди."),
        F("offset", "Точка вылета [x, y], px", "vec2", "8, -4", "От центра моба; x — в сторону взгляда."),
    ]),
    "leap": ("Прыжок", "Прыжок на землю рядом с игроком с ударом при приземлении (летун делает рывок).", [
        F("land_offset", "Приземлиться от игрока, px", "num", "40", "На каком расстоянии от игрока."),
        F("air_time", "Время в полёте, с", "num", "0.6", "Чем больше, тем выше дуга."),
        F("radius", "Радиус удара, px", "num", "60", "Радиус зоны при приземлении."),
        F("gravity", "Гравитация прыжка", "num", "1800", "Сила тяжести во время прыжка."),
        F("track", "Цель следует за игроком", "bool", "да", "Пока замах, точка приземления следует за игроком."),
    ]),
}
# значения по умолчанию для полей, которые зависят от вида атаки (показываются серым)
ATTACK_DEFAULTS = {
    "melee": {"range": "reach[0] + w/2 + 6", "range_y": "60"},
    "circle": {"range": "radius × 0.9", "range_y": "999"},
    "shoot": {"range": "420", "range_y": "260", "active": "0.05"},
    "leap": {"range": "300", "range_y": "220", "min_range": "60"},
}
ATTACK_TEMPLATES = {
    "melee": {"type": "melee", "windup": 0.35, "active": 0.12, "recovery": 0.35, "cooldown": 1.2, "damage": 10, "reach": [40, 28]},
    "circle": {"type": "circle", "radius": 70, "windup": 0.7, "active": 0.15, "recovery": 0.6, "cooldown": 2.2, "damage": 14, "knockback": 300},
    "shoot": {"type": "shoot", "projectile": "bolt", "windup": 0.5, "cooldown": 2.0, "damage": 8, "range": 360},
    "leap": {"type": "leap", "range": 300, "min_range": 90, "windup": 0.45, "air_time": 0.6, "land_offset": 40, "radius": 55,
             "damage": 12, "recovery": 0.25, "cooldown": 2.8},
}
ACTIVE_ANIM = {"leap": "jump"}          # как называется анимация фазы «удар»: Attack.anim() в attacks.py (по умолчанию attack)
PHASES = ("windup", "active", "recovery")
PHASE_RU = {"windup": "замах", "active": "удар", "recovery": "отдых"}

STD_STATES = [("idle", "Покой"), ("move", "Ходьба"), ("jump", "Прыжок / падение"), ("hurt", "Получение урона"), ("death", "Смерть")]
STD_NAMES = {n for n, _ in STD_STATES} | {"walk", "windup", "attack", "recovery"}

MOB_TEMPLATE = {"name": "Новый моб", "hp": 30, "w": 24, "h": 32, "speed": 80, "color": [180, 180, 180], "weight": 1, "mass": 2,
                "contact": 6, "draw": [32, 40], "move": {"type": "chase", "sight": 360}, "attacks": [], "xp": 50}
ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


# ---------------------------------------------------------------- значения полей
def get_path(d, key, default=None):
    """d["a"]["b"] по ключу "a.b" (нет — default)."""
    for part in key.split("."):
        if not isinstance(d, dict) or part not in d: return default
        d = d[part]
    return d


def set_path(d, key, value):
    """Записать значение по ключу "a.b"; value=None удаляет ключ (и пустые вложенные словари)."""
    parts = key.split("."); chain = [d]
    for p in parts[:-1]:
        nxt = chain[-1].get(p)
        if not isinstance(nxt, dict):
            if value is None: return
            nxt = chain[-1][p] = {}
        chain.append(nxt)
    if value is None: chain[-1].pop(parts[-1], None)
    else: chain[-1][parts[-1]] = value
    for i in range(len(parts) - 1, 0, -1):          # убрать опустевшие вложенные словари
        if not chain[i]: chain[i - 1].pop(parts[i - 1], None)


def parse_num(text, integer=False):
    """'' -> (True, None); '12' -> 12; '0.35' / '0,35' -> 0.35; мусор -> (False, None)."""
    t = str(text).strip().replace(",", ".")
    if not t: return True, None
    try:
        v = float(t)
    except ValueError:
        return False, None
    if integer or re.fullmatch(r"-?\d+", t): return True, int(round(v))
    return True, v


def fmt_num(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e9: return str(v)     # 2.0 остаётся 2.0, как в файле
    return str(v)


def parse_points(text):
    """Строки «dx dy» -> [[dx, dy], ...]; пусто -> None; ошибка -> False."""
    pts = []
    for line in str(text).splitlines():
        line = line.strip().replace(",", " ")
        if not line: continue
        parts = line.split()
        if len(parts) != 2: return False
        ok1, a = parse_num(parts[0]); ok2, b = parse_num(parts[1])
        if not (ok1 and ok2 and a is not None and b is not None): return False
        pts.append([a, b])
    return pts or None


def points_text(pts):
    return "\n".join(f"{fmt_num(p[0])} {fmt_num(p[1])}" for p in pts) if isinstance(pts, list) else ""


def unique_name(base, taken):
    """base, base_2, base_3 ... — первое не занятое имя."""
    if base not in taken: return base
    n = 2
    while f"{base}_{n}" in taken: n += 1
    return f"{base}_{n}"


# ---------------------------------------------------------------- файл data/mobs.json
def load_mobs(path=None):
    """{id: описание} из data/mobs.json в исходном порядке. Нет файла — пустой словарь."""
    path = Path(path or DATA_DIR / "mobs.json")
    if not path.exists(): return {}
    return json.loads(path.read_text(encoding="utf-8"))


def dump_mobs(mobs):
    """Текст файла — ровно в том формате, в каком он лежит в репозитории (indent=2, UTF-8, перевод строки в конце)."""
    return json.dumps(mobs, ensure_ascii=False, indent=2) + "\n"


def save_mobs(mobs, path=None):
    path = Path(path or DATA_DIR / "mobs.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_mobs(mobs), encoding="utf-8")


def load_projectiles(data_dir=None):
    try: return list(json.loads((Path(data_dir or DATA_DIR) / "projectiles.json").read_text(encoding="utf-8")))
    except Exception: return []


def fix_skin(path, assets=None):
    """Чинит путь к скину: обратные слеши -> «/», без расширения -> добавить .png, если такой файл есть.
    Так в data/mobs.json у rotling написано `mobs\\rotling\\rotling` (одиночные слеши): JSON читает `\\r` как символ
    возврата каретки, и в строке остаётся «mobs<CR>otling<CR>otling» — управляющие символы \\r \\n \\t \\b \\f
    превращаются обратно в «/r» «/n» «/t» «/b» «/f». Возвращает исправленный путь (или исходный, если чинить нечем)."""
    assets = Path(assets or ASSETS_DIR)
    if not isinstance(path, str) or not path: return path
    fixed = path
    for ctrl, letter in (("\r", "r"), ("\n", "n"), ("\t", "t"), ("\b", "b"), ("\f", "f")): fixed = fixed.replace(ctrl, "/" + letter)
    fixed = fixed.replace("\\", "/")
    if (assets / fixed).is_file(): return fixed
    if not fixed.lower().endswith(".png") and (assets / (fixed + ".png")).is_file(): return fixed + ".png"
    return fixed if fixed != path and (assets / fixed).exists() else path


def new_mob_id_ok(mob_id, mobs):
    if not mob_id or not ID_RE.match(mob_id): return "ID: только латинские буквы, цифры, _ и -"
    if mob_id in mobs: return f"Моб «{mob_id}» уже есть"
    if mob_id.startswith("__"): return "ID не должен начинаться с «__» (служебные имена)"
    return None


def new_mob():
    return copy.deepcopy(MOB_TEMPLATE)


def new_attack(kind):
    return copy.deepcopy(ATTACK_TEMPLATES[kind])


def attack_title(i, a):
    t = ATTACK_TYPES.get(a.get("type"), (str(a.get("type")),))[0]
    return f"{i + 1}. {a['id']} — {t}" if a.get("id") else f"{i + 1}. {t}"


def change_attack_type(a, new_type):
    """Сменить вид атаки: общие поля остаются, поля старого вида (которых нет у нового) удаляются."""
    old = a.get("type")
    own = lambda t: {f.key for f in ATTACK_TYPES.get(t, ("", "", []))[2]}
    for k in own(old) - own(new_type): a.pop(k, None)
    a["type"] = new_type


def phase_gen(a, phase):
    """Имя «общей» анимации фазы атаки: windup / <attack|jump> / recovery."""
    return ACTIVE_ANIM.get(a.get("type"), "attack") if phase == "active" else phase


def phase_duration(a, phase):
    """Сколько секунд фаза идёт в игре (так же считает Mob.anim_states: для удара — air_time или active)."""
    if phase == "windup": return float(a.get("windup", .4))
    if phase == "recovery": return float(a.get("recovery", .4))
    return float(a.get("air_time", a.get("active", .12)))


def active_length(a):
    """Реальная длина фазы удара (стрельба очередью длится дольше `active`)."""
    d = phase_duration(a, "active")
    if a.get("type") == "shoot": d = max(d, (int(a.get("burst", 1)) - 1) * float(a.get("burst_gap", .15)) + .05)
    return d


# ---------------------------------------------------------------- анимации
def natural_key(p):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", Path(p).name)]


def list_frames(rel, assets=None):
    """Кадры по пути assets/<rel>: папка (*.png), шаблон со «*» или один файл — как anim.frames() в игре."""
    assets = Path(assets or ASSETS_DIR)
    if not rel: return []
    if "*" in rel: files = sorted(assets.glob(rel), key=natural_key)
    elif (assets / rel).is_dir(): files = sorted((assets / rel).glob("*.png"), key=natural_key)
    elif (assets / rel).is_file(): files = [assets / rel]
    else: files = []
    return [f.relative_to(assets).as_posix() for f in files]


def anim_key(mob, name):
    """Под каким ключом anims лежит анимация `name`: для ходьбы допустимы оба имени (move / walk), как в игре."""
    anims = mob.get("anims", {})
    return "walk" if name == "move" and name not in anims and "walk" in anims else name


def anim_spec(mob, name):
    spec = mob.get("anims", {}).get(anim_key(mob, name))
    if isinstance(spec, str): spec = {"frames": spec}
    return dict(spec or {})


def anim_source(mob_id, mob, name, assets=None):
    """(путь, вид): откуда игра берёт кадры анимации. Вид: dir | glob | file | none (кадров нет)."""
    assets = Path(assets or ASSETS_DIR)
    key = anim_key(mob, name); spec = anim_spec(mob, name)
    rel = spec.get("frames") or f"mobs/{mob_id}/{key}"
    if not list_frames(rel, assets) and name == "move" and key == "move" and list_frames(f"mobs/{mob_id}/walk", assets):
        rel = f"mobs/{mob_id}/walk"
    frames = list_frames(rel, assets)
    kind = "none" if not frames else "glob" if "*" in rel else "file" if (assets / rel).is_file() else "dir"
    return rel, kind


def own_folder(mob_id, rel):
    """Папка кадров лежит в assets/mobs/<id>/ — только такие папки редактор перенумеровывает и чистит."""
    rel = rel.replace("\\", "/").strip("/")
    return "*" not in rel and rel.startswith(f"mobs/{mob_id}/") and not rel.lower().endswith(".png")


def set_anim_spec(mob, name, **kw):
    """Изменить поля записи анимации (frames / fps / loop); None удаляет поле. Запись создаётся при первой правке;
    у стандартных состояний пустая запись удаляется, у своих — остаётся (иначе анимация «пропадёт» из списка)."""
    key = anim_key(mob, name); anims = mob.setdefault("anims", {})
    spec = anim_spec(mob, name)
    for k, v in kw.items():
        if v is None: spec.pop(k, None)
        else: spec[k] = v
    if not spec and key in STD_NAMES: anims.pop(key, None)
    else: anims[key] = spec
    if not anims: mob.pop("anims", None)


def custom_anim_names(mob_id, mob, assets=None):
    """Свои анимации: из записей anims и из подпапок assets/mobs/<id>/ (со стандартными именами не пересекаются)."""
    assets = Path(assets or ASSETS_DIR)
    names = [n for n in mob.get("anims", {}) if n not in STD_NAMES]
    folder = assets / "mobs" / mob_id
    if folder.is_dir():
        for sub in sorted(folder.iterdir()):
            if sub.is_dir() and sub.name not in STD_NAMES and sub.name not in names and any(sub.glob("*.png")): names.append(sub.name)
    return names


def anim_names_all(mob_id, mob, assets=None):
    """Все имена анимаций, которые можно назначить фазе атаки (свои + назначенные в атаках)."""
    names = custom_anim_names(mob_id, mob, assets)
    for a in mob.get("attacks", []):
        for v in a.get("anims", {}).values():
            if isinstance(v, str) and v and v not in names: names.append(v)
    return names


def preview_entries(mob_id, mob, assets=None):
    """Что можно посмотреть в окне с мобом: стандартные состояния, свои анимации, фазы каждой атаки и атака целиком."""
    out = [{"kind": "state", "state": n, "label": f"{t} ({n})"} for n, t in STD_STATES]
    out += [{"kind": "state", "state": n, "label": f"Своя: {n}"} for n in anim_names_all(mob_id, mob, assets)]
    for i, a in enumerate(mob.get("attacks", [])):
        title = attack_title(i, a)
        out += [{"kind": "phase", "i": i, "phase": ph, "label": f"Атака {title}: {PHASE_RU[ph]}"} for ph in PHASES]
        out.append({"kind": "attack", "i": i, "label": f"Атака {title}: вся атака"})
    for k, e in enumerate(out): e["key"] = f"{e['kind']}:{e.get('state', '')}{e.get('i', '')}{e.get('phase', '')}"
    return out


def _renumber(paths, folder):
    """Переименовать файлы в 1.png, 2.png ... в заданном порядке (через временные имена, без коллизий)."""
    tmp = []
    for i, p in enumerate(paths):
        t = folder / f"__tmp_{i}.png"; Path(p).rename(t); tmp.append(t)
    for i, t in enumerate(tmp, 1): t.rename(folder / f"{i}.png")


def frame_files(rel, assets=None):
    assets = Path(assets or ASSETS_DIR)
    return [assets / r for r in list_frames(rel, assets)]


def add_frames(rel, sources, assets=None):
    """Скопировать PNG в папку assets/<rel> в конец анимации; потом все кадры нумеруются заново 1..n. Возвращает число добавленных."""
    assets = Path(assets or ASSETS_DIR); folder = assets / rel; folder.mkdir(parents=True, exist_ok=True)
    cur = frame_files(rel, assets); added = []
    for n, src in enumerate(sorted(map(Path, sources), key=natural_key)):
        dst = folder / f"__new_{n}.png"; shutil.copyfile(src, dst); added.append(dst)
    _renumber(cur + added, folder)
    return len(added)


def remove_frame(rel, index, assets=None):
    assets = Path(assets or ASSETS_DIR); files = frame_files(rel, assets)
    if not 0 <= index < len(files): return
    files[index].unlink(); del files[index]
    _renumber(files, assets / rel)


def move_frame(rel, index, delta, assets=None):
    """Сдвинуть кадр на delta позиций (−1 — раньше, +1 — позже). Возвращает новый индекс."""
    assets = Path(assets or ASSETS_DIR); files = frame_files(rel, assets); j = index + delta
    if not (0 <= index < len(files) and 0 <= j < len(files)): return index
    files[index], files[j] = files[j], files[index]
    _renumber(files, assets / rel)
    return j


def copy_mob(mobs, old_id, new_id, copy_assets=True, assets=None):
    """Копия моба. С copy_assets копируется и папка assets/mobs/<old>/, а пути mobs/<old>/... в копии переписываются."""
    assets = Path(assets or ASSETS_DIR); d = copy.deepcopy(mobs[old_id])
    src, dst = assets / "mobs" / old_id, assets / "mobs" / new_id
    if copy_assets and src.is_dir() and not dst.exists():
        shutil.copytree(src, dst)
        def rewrite(x):
            if isinstance(x, str): return x.replace(f"mobs/{old_id}/", f"mobs/{new_id}/").replace(f"mobs\\{old_id}\\", f"mobs/{new_id}/")
            if isinstance(x, list): return [rewrite(i) for i in x]
            if isinstance(x, dict): return {k: rewrite(v) for k, v in x.items()}
            return x
        d = rewrite(d)
    return d


def import_skin(src, mob_id, assets=None):
    """Положить выбранный PNG в assets/mobs/<id>/ (если он ещё не в assets) и вернуть путь для поля skin."""
    assets = Path(assets or ASSETS_DIR); src = Path(src).resolve()
    try: return src.relative_to(assets.resolve()).as_posix()
    except ValueError: pass
    folder = assets / "mobs" / mob_id; folder.mkdir(parents=True, exist_ok=True)
    dst = folder / f"{mob_id}.png"
    if dst.exists() and dst.resolve() != src:
        dst = folder / (unique_name(f"{mob_id}_skin", {p.stem for p in folder.glob("*.png")}) + ".png")
    shutil.copyfile(src, dst)
    return dst.relative_to(assets).as_posix()


# ---------------------------------------------------------------- проверки и ссылки
def references(mob_id, data_dir=None):
    """Где моба упоминают карты: ['maps.json: символ «r»', 'spikes: mob_pool', ...]."""
    data_dir = Path(data_dir or DATA_DIR); out = []
    files = [data_dir / "maps.json"] + sorted((data_dir / "maps").glob("*.json"))
    for f in files:
        try: d = json.loads(f.read_text(encoding="utf-8"))
        except Exception: continue
        for ch, e in (d.get("legend") or {}).items():
            if isinstance(e, dict) and e.get("mob") == mob_id: out.append(f"{f.stem}: символ «{ch}» (легенда)")
        pool = d.get("mob_pool")
        if (isinstance(pool, dict) and mob_id in pool) or (isinstance(pool, list) and mob_id in pool): out.append(f"{f.stem}: mob_pool")
    return out


def validate(mobs, assets=None, projectiles=()):
    """Список предупреждений [(id моба, текст)]. Сохранять они не мешают — это подсказки."""
    assets = Path(assets or ASSETS_DIR); out = []
    for mid, m in mobs.items():
        add = lambda t: out.append((mid, t))
        if not isinstance(m.get("hp"), (int, float)) or m["hp"] <= 0: add("здоровье должно быть больше 0")
        for k in ("w", "h"):
            if not isinstance(m.get(k), (int, float)) or m[k] <= 0: add(f"хитбокс: {k} должно быть больше 0")
        skin = m.get("skin")
        if skin and not (assets / skin).is_file(): add(f"скин не найден: {skin}")
        if m.get("move", {}).get("type", "chase") not in MOVES: add(f"неизвестный вид движения: {m['move'].get('type')}")
        ids = [a.get("id") for a in m.get("attacks", []) if a.get("id")]
        for d in {i for i in ids if ids.count(i) > 1}: add(f"два раза атака с id «{d}»")
        for i, a in enumerate(m.get("attacks", [])):
            t = attack_title(i, a)
            if a.get("type") not in ATTACK_TYPES: add(f"атака {t}: неизвестный вид «{a.get('type')}»"); continue
            if a.get("next") and a["next"] not in ids: add(f"атака {t}: «следующая» ссылается на несуществующий id «{a['next']}»")
            pr = a.get("projectile")
            if a.get("type") == "shoot" and isinstance(pr, str) and projectiles and pr not in projectiles: add(f"атака {t}: нет снаряда «{pr}»")
            for ph, name in (a.get("anims") or {}).items():
                if isinstance(name, str) and name and anim_source(mid, m, name, assets)[1] == "none":
                    add(f"атака {t}: у анимации «{name}» нет кадров (фаза {ph})")
    return out
