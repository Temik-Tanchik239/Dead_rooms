Ты — pi-агент в проекте DEAD ROOMS (Python/Pygame-ce рогалик, каталог C:/Users/artem/Desktop/DEAD_ROOMS).
ЗАДАЧА: создай НОВЫЙ модуль save_io.py — сериализация/восстановление забега (система сохранений).

СНАЧАЛА прочитай отчёт аудитора: multiagent/audit_own.md (разделы 1, 2, 5) — там точные списки полей Game/Player/Campaign/GameMap и форматы сериализации мобов/дропов/ящиков. Также изучи: main.py (Game ~529, new_game ~575, Player ~69), maps.py (Campaign ~434, GameMap), multiplayer.py (HostSession.snapshot и ClientSession.apply_world — образец сериализации мобов/дропов/контейнеров/мехов), inventory.py (init ~162, bag ~153, equip, resources), crossbow.py, bard.py, core.py (apply_character ~111, CHAR ~78).

Контракт модуля (строго эти имена, главный агент вызовет их из main.py):

```python
SAVES_DIR                       # pathlib.Path: <папка игры>/saves (учти sys.frozen: рядом с exe); создаётся при импорте
def list_saves() -> list[dict]  # новые первыми: [{"id": "save_1" (имя файла без .json), "name": чел. имя,
                                #   "time": "ГГГГ-ММ-ДД ЧЧ:ММ", "loop": int, "char": id текущего героя,
                                #   "chars": [id всех героев забега], "level": {cid: уровень}, "file": полный путь}]
def save(g, label=None) -> dict # полный снапшот забега g -> saves/save_<N>.json; возвращает meta (как в list_saves)
def restore(g, save_id) -> None # поднимает забег из файла: camp/room/герой/g.heroes; g.menu_mode=None; последним —
                                #   apply_character + g.pl = восстановленный Player
def snapshot_player(pl) -> dict # JSON-сериализуемый снапшот героя (его будут звать и из swap.py!)
def restore_player(pl, snap) -> None  # восстанавливает героя ПО СЛОВУ (объект pl уже создан)
```

Формат JSON-файла:
{"version": 1, "created": ISO-время, "name": label, "loop": camp.loop, "room": id текущей комнаты,
 "pos": [x, y] героя, "char": CHAR["id"], "heroes": {cid: snapshot_player(pl)} — снапшот КАЖДОГО героя забега
 (g.heroes из swap.py — обычный dict cid->dict, сохраняй как есть; если swap.py ещё нет — только текущий герой),
 "came_from": {...camp.came_from...}, "maps": {mid: {"visited", "cleared", "spawned", "locked", "boss_spawned",
 "mobs": [[kind, x, y, scale, hp, dir], ...], "drops": [["W", x, y, wid] | ["R", x, y, rid], ...],
 "ct": containers.state(r), "mc": mechs.state(r)} для каждой посещённой карты}}

ВАЖНЫЕ ПРАВИЛА:
1. НЕ импортируй main.py (циркулярный импорт!) — функцию-конструктор Player объявляй лениво: restore() принимает g и зовёт g.Player() (в main.py это есть: Game.Player = Player).
2. Ничего кроме save_io.py не создавай и не редактируй.
3. restore(): сначала apply_character(cid текущего героя сохранения) + clear_cache (anim.clear_cache и inventory.clear_cache), g.camp = Campaign(loop) — затем восстановить карты через camp.get(mid) и проставить visited/cleared/spawned/locked/boss_spawned, drops (maps.Drop(x,y,wid) / crafting.ResourceDrop(x,y,rid)), ящики и мехи по форматам из multiplayer.py apply_world (~972). Мобы: если карта не cleared и есть сохранённые мобы — создать Mob(kind,x,y,scale) с hp (mob.py); если не cleared и мобов в сохранении нет — оставить spawned=False (мобы заспавнятся заново при входе). ПОМНИ про запертые двери: locked=True допустим только при живых мобах.
4. Текущая комната: g.go(room_id, None) — затем позицию героя из "pos".
5. Временное НЕ сохранять: fx, projs, pl.atk/atk-анимации, pl.channel/hold, pl.invis, pl.clones, pl.grab, pl.buf, pl.shield_time, bard-«играет ноту», corpses, turrets (обоснуй выбор в отчёте).
6. Постоянное сохранять ВСЁ: hp/maxhp/mana/level/xp/xp_next/skills/item_skills/skill_index/slots/bag/equip/resources/last_weapon/goggles/hold_pool/hold_rest/crossbow-состояние (см. crossbow.init, pl.xb_*)/bard-усилители pl.amps.
7. Русские тексты ошибок/сообщений; кодировка UTF-8; indent=2.
8. Тесты: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe — прогони полный цикл: создать Game (import core; core.apply_character("knight"); import main as M; g=M.Game(); g.menu_mode=None), выдать герою предметы в bag/обидные значения level/xp, save(g), изменить состояние, restore(g, id) — проверить hp/bag/skills/room/loop/g.heroes, повторно save → list_saves видит оба файла. Так же смени героя (core.apply_character("mage"); g.pl=M.Player()) и проверь, что restore вернёт рыцаря с его bag.
9. py_compile save_io.py обязательно.
Финальный ответ: краткий отчёт (формат файла, что сохраняется/нет, результаты тестов) + строка RESULT_OK.
