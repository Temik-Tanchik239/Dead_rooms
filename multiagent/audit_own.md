# Аудит состояния для системы сохранений (составил главный агент)

Проект: DEAD ROOMS (Python 3.15, pygame-ce 2.5.8). Venv: ./.venv/Scripts/python.exe.
Тесты headless: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe

## 1. Состояние забега

### main.py — Game (~529)
Создаётся в `__init__` (~547): scr/view/fonts/debug/cam/grid, show_world, controls_open, waiting_for_bind,
hud_edit/hud_drag/hud_selected, veil, net/mp_*, dev, mp_name/mp_ip, clock, level_menu/level_choices/
level_menu_level/skill_unlock_anim, menu_mode ("start"|"pause"|None + новые режимы), menu_selection,
menu_edit, menu_drag, menu_selected, ассеты меню (menu_background, menu_veil, menu_button,
menu_button_selected — из assets/menu/*).
`new_game(s, loop=0, character=None)` (~575): inv_open/inv_hold/crafting/placing/place_lock/place_hold/
craft_sel сброс; pl = Player(); camp = Campaign(loop); room=None; done=False; fx=FX(); projs=[];
warn_t; go(first, None).
**Сохранять**: pl, camp, room.id (и позицию героя), done. **Временное**: fx, projs, warn_t, dev,
menu_*, hud_*, net (сохр. только в одиночной игре).

### maps.py — Campaign (~434)
Поля: loop, maps {mid: GameMap}, came_from {mid: prev_mid}. Методы: order (свойство — из CFG["maps"]["order"]),
first, scale() = 1 + loop_scale*loop, get(mid) (создаёт GameMap), resolve(cur, target), reload().
Восстановление: camp = Campaign(loop); для каждого сохранённого mid — camp.get(mid) и проставить поля.

### maps.py — GameMap (~тот же файл)
В __init__: id, d (из CFG["map_defs"]), name, pos, scale, legend, chars/info (сетка из md["rows"]),
width/height/width_px/height_px, exits (find_exits), lights (lighting.find_lights).
**Динамическое**: visited, cleared, spawned, locked (все False при создании), mobs [], corpses [], drops [],
turrets [] (турели инженера — живут до выхода из комнаты, НЕ сохранять), boss_spawned=False.
Дропы при спавне: `"item"` → Drop(cx, (r+1)*T-14, wid) — maps.py ~после 455; `"resource"` →
crafting.ResourceDrop(cx, (r+1)*T-10, rrid).
**Сохранять по каждой карте**: visited/cleared/spawned/locked/boss_spawned, mobs, drops, containers, mechs.
**Восстановление**: camp.get(mid) создаёт GameMap из data/maps/<mid>.json; проставить сохранённые поля.

### Мобы (mob.py)
Mob(kind, x, y, scale, room=None) — kind = строка id из CFG["mobs"]. Постоянное: kind, x, y, scale,
hp/maxhp, face/dir, state. Образец сериализации мобов — multiplayer.py, HostSession.snapshot()
(строки "mobs": [nid, kind, x, y, hp, maxhp, dir, state, ...]) — смотри точно в файле.
**Corpses — НЕ сохранять** (временная анимация).

### Дропы
- maps.py Drop(x, y, wid) — оружие (см. maps.py:170).
- crafting.py ResourceDrop(x, y, rid) (~70) — ресурс инженера.
- В r.drops лежат и те и другие — при сериализации маркировать: ["W", x, y, wid] / ["R", x, y, rid].
- Внимание: multiplayer.py:739 сериализует d.wid только у Drop (isinstance) — ресурсы клиент не получает.

### Ящики и механизмы
- containers.py: `state(room)` (~225) → {uid: [hp, opened, dy]}; `apply_state(room, st)` (~232) — восстановление.
- mechs.py: `state(room)` (~311) → {id: [on, plat_y]}; `apply_state(room, st)` (~318).
- Контейнеры появляются при первом спавне комнаты (ROLL_SPAWN) — r.spawn() вызовется, если spawned=False.

### Позиция героя
s.room.id + s.pl.x/y; восстановление: g.go(mid, None) (ставит respawn/place), затем pl.x/pl.y из сейва.
s.respawn/s.armed — временные (пересчитаются в go()).

## 2. Состояние героя (сохраняется на КАЖДОГО героя забега отдельно)

### main.py — Player (~69)
Постоянное: hp, maxhp (из ch hitbox+пассивки), mana, level, xp, xp_next, skills, item_skills,
skill_index, skill_cooldowns, slots [ЛКМ, ПКМ], bag (список id/None), equip {slot: wid}, resources
{rid: n}, last_weapon, goggles, hold_pool {sid: запас}, hold_rest {sid: таймер}, char_id.
Временное (НЕ сохранять): buf, atk, combo, hitbox-анимация, anim/anim_t, inv/st/lock/coy/stun/drop_t,
grab, channel, hold, hold_latch, shield_*, invis, clones, xb_kick/xb_notice/xb_held/xb_lock/hooks,
bd_note/bd_play/bd_tick/bd_notice/bd_lock, pid/name/revive/downed/tp/hitc/kb, air_t/air_jumps, aim.

### Подсистемы (см. их init)
- inventory.init(pl) (~162): pl.bag = [None]*bag_size; pl.equip = {}; pl.resources = {}; стартовые
  предметы из assets/inventory.json в bag.
- crossbow.init(pl): pl.xb_ammo [0,0], pl.xb_cd [0.0,0.0], xb_kick, xb_notice, hooks, xb_held, xb_lock.
  Сохранять: xb_ammo, xb_cd. Остальное — временное.
- bard.init(pl): pl.bd_note, bd_play, bd_tick, bd_notice, bd_lock, pl.amps [] (усилители — навык amp;
  amp'ы — объекты bard с полями; если сериализация сложная — amps НЕ сохранять, обоснуй в отчёте).
- clone.py: pl.clones — НЕ сохранять (транзиентный бой-помощник).
- invisibility.init(pl): pl.invis — НЕ сохранять.
- Пассивки экипировки пересчитываются из pl.equip (inventory.stat/stat_mult) — отдельно не хранить.

### Смена персонажа посреди забега
- core.py: apply_character(cid) (~111) — mutate CFG["character"] (+ CFG["char_looks"] и пр.);
  _set_char (~126); CHAR = {"id": None} (~78); char_ids() — список героев; char_def(cid);
  char_player_cfg(cid) (~105).
- ПОСЛЕ apply_character нужен clear_cache() — в main.py импортирован `from anim import clear_cache`
  (main.py:9); в new_game: `apply_character(...); clear_cache()`. inventory.clear_cache() — сброс
  кэша конфига инвентаря (отдельный).
- Player() читает CFG["character"] (hitbox, weapons, spellcaster/crossbows/bard, base_skills,
  model_scale) — поэтому смена героя = снапшот СТАРОГО pl ДО apply_character, затем НОВЫЙ Player().
- SETTINGS["last_character"] = cid; g.save_settings() — как в characters.py:117.
- Хитбокс меняется: pl.H0 различается; главное — позицию ставить после создания, на пол.

## 3. Интеграция в main.py (исполнители НЕ правят main.py — это делает главный агент)

- key() (~806): ветка `if s.menu_mode is not None:` (~817) — роутинг новых режимов сюда.
- menu_action() (~886): "continue"/"new"/"multiplayer"/"exit"; добавить "saves"/"swap"/"save"/"load"/"menu".
- menu_event() (~940): `options = [...]` (~943) и draw_menu() (~996 options) — списки кнопок start/pause.
- menu_layout() (~903): настройки "menu_layout" (start) и "menu_layout_pause" (pause) в data/settings.json.
- Esc ставит pause (~888). K_r — рестарт. F5 — reload данных (НЕ трогать).
- mp.MENU_MODES = ("mp", "connect") — образец роутинга: key() ~816, event() ~942, draw_menu() ~985.
- draw_world: `if s.menu_mode is not None: s.draw_menu()` (~1171) — меню рисуется ПОВЕРХ мира.
- В сетевой игре (s.net) сохранения/смена героя/загрузка НЕДОСТУПНЫ (guard).

## 4. Риски
- Циркулярный импорт: save_io НЕ должен импортировать main.py (Player берём через g.Player()).
- locked=True при пустых мобах = застревание (двери заперты) — проверять при restore.
- Ресурсные дропы vs оружейные в r.drops — маркировать тип.
- Клоны/гарпуны/сильд — сброс при восстановлении (иначе висящие ссылки на старые объекты).
- pl.bag: None-ячейки обязательны (bag_size из assets/inventory.json).
- apply_character перетирает поля героя — всегда создавать Player заново после смены героя.
