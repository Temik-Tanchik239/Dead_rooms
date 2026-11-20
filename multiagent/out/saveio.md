Готово. Итоговый отчёт:

## Модуль `save_io.py` (создан, ~430 строк)

**Контракт реализован строго:** `SAVES_DIR` (Path, `<папка игры>/saves`, в frozen-сборке — рядом с EXE, через `core.BASE`; создаётся при импорте), `list_saves()`, `save(g, label=None)`, `restore(g, save_id)`, `snapshot_player(pl)`, `restore_player(pl, snap)`. Циркулярного импорта main.py нет — Player создаётся через `g.Player()`.

**Формат JSON** (`saves/save_<N>.json`, UTF-8, `ensure_ascii=False`, `indent=2`, version 1): `version, created (ISO), name, loop, room, pos [x,y], char, heroes {cid: снапшот}, came_from, maps {mid: {visited, cleared, spawned, locked, boss_spawned, mobs [[kind,x,y,scale,hp,dir]], drops [["W",x,y,wid]|["R",x,y,rid]], ct, mc}}`. Форматы `ct`/`mc` — те же `containers.state()`/`mechs.state()`, что в сети; `restore` применяет их через `apply_state`. Scale моба не хранится в `Mob` — вычисляется как `maxhp / hp_из_JSON`, при восстановлении HP ставится сохранённое.

**Ключевые решения:**
- `ROLL_SPAWN=False` на время восстановления карт (как у клиента сети) — сейв решает, какие ящики появились; лишние убирает `apply_state`; флаг возвращается в `finally`.
- Guard запертых дверей: `locked=True` сохраняется и восстанавливается **только** при живых мобах (иначе двери отпираются) — защита от запертой пустой комнаты.
- Мангарт восстанавливается с `room=` (руки строятся от раскладки карты); манекены F6 (`is_dummy`) и умирающие (hp≤0) не сохраняются.
- Порядок `restore`: `apply_character` → `anim/inventory.clear_cache` → `Campaign(loop)` + came_from → карты → `g.pl = g.Player()` → `g.go(room, None)` → позиция из `pos` → `restore_player` (после `go`, т.к. `place()` сбрасывает гарпуны/усилители) → `g.heroes` (снапшоты; работает и с будущим swap.py) → `menu_mode=None` + сброс транзиентных хвостов (inv/crafting/level_menu/fx/projs).

**Сохраняется (всё постоянное):** hp/maxhp/mana, level/xp/xp_next, skills/item_skills/skill_index/skill_cooldowns, slots/bag (с None-ячейками, нормализация под bag_size)/equip/resources, last_weapon, goggles, hold_pool/hold_rest, bd_note, pl.amps (обычные dict'ы — сериализация тривиальна, потому сохранены; на восстановлении сбрасываются в падение на пол), xb_ammo/xb_cd. Бонусы экипировки отдельно не хранятся — пересчитываются `on_equipment_changed` → `refresh_mana`, hp/mana зажимаются в новые максимумы.

**Не сохраняется (транзиентное):** fx, projs, corpses, turrets (живут до выхода из комнаты — их не переносит и сетевой снимок), манекены, бой игрока (atk/комбо/анимации/buf), channel/hold/hold_latch, гарпуны и отдача арбалетов, щит, невидимость, клоны, «играющая нота» барда (bd_play/bd_tick), сетевые поля pid/name/revive и т.п.

**Тесты (headless, dummy SDL) — все пройдены:** рыцарь с предметами/level 7/xp 55/уроном/дропами на полу и 6 мобами в env_8_0 → `save` (save_1) → порча состояния (урон, очистка bag, круг 2, другая комната) → `restore`: hp 37.5, mana 12, level/xp, bag, goggles, hold_pool/rest, комната, loop=0, позиция (±0.1), мобы (вид/hp 33.5), дроп на месте, `g.heroes` заполнен, `menu_mode=None`. Повторный `save` → save_2, `list_saves` возвращает `[save_2, save_1]` (новые первыми). Смена героя на мага (`apply_character("mage"); g.pl = Player()`) → `restore` вернул рыцаря с его рюкзаком. Guard `locked` без мобов работает. `py_compile` — OK. Тестовые файлы из `saves/` удалены.

RESULT_OK