Полный аудит выполнен и сохранён в `multiagent/out/audit_save.md` (640 строк, только чтение — ни один файл проекта не изменён).

## Сводка результата

**Что изучено** (все ключевые файлы прочитаны построчно): `main.py` (класс `Player` 69, класс `Game` 529, меню 805–1010, `step` 717), `maps.py` (`GameMap` 153, `Drop` 134, `Campaign` 436), `mob.py` (25/271), `multiplayer.py` (`snapshot` 687, `apply_world` 957, `player_obj` 979), `core.py` (`apply_character` 111, `_set_char` 126, `CHAR` 78, `use_char` 136), `inventory.py` (%`init` 162, `stat` 259, `sync_skills` 297), `crossbow.py`, `bard.py`, `spells.py`, `clone.py`, `invisibility.py`, `containers.py` (225/229), `mechs.py` (311/316), `crafting.py` (`ResourceDrop` 70, `Turret` 365), `characters.py`, `data/characters.json`, `assets/inventory.json`, `data/settings.json`, `data/maps.json`.

**Ключевые находки для исполнителей**:
1. **Формат сериализации забега** — эталон `multiplayer.snapshot()`: мобы `[kind,x,y,dir,hp,maxhp,flash,anim,anim_t,anim_p,act,hands,invis]`; восстановление комнаты — образец `apply_world` (`create`→`apply_state`→`r.build()` обязателен, иначе клетки ящиков/дверей не встанут в физику).
2. **Игрок** — восстановление ТОЛЬКО `with use_char(cid): p = Game.Player()` + переписывание полей (образец `player_obj`/`make_player`); после `equip` → `inventory.sync_skills` + `refresh_mana(True)`; `item_skills` и `skill_index` обязательны; готовые сериализаторы `spells.hold_net`, `crossbow.net_pack`, `bard.net_pack`.
3. **Смена героя** — пересоздавать объект, не «перекрашивать» живого (у героев разные слоты рук/подсистемы); безопасный сценарий в разделе 3.3.
4. **Интеграция** — минимальная правка 4 мест в `main.py` (`menu_event` 943, `draw_menu` 996, `menu_layout` 906, `menu_action``menu_action` 889) + `menu_layout` defaults (пауза → 5 кнопок `save/load/continue/char/exit`), с фильтром `if s.net:` (сохранение/загрузка/смена героя в сети скрывать и игнорировать). `F5`/`K_r`/`K_RETURN(done)` не трогать.

**Риски, которые критично учесть**:
- В `spells.py` **два дублирующих блока** «потоков» (строки 216–394 и 427–604) — живёт второй; патчить hold-логику только там.
- `Game.place`/`go` вызывают `crossbow.release_all` и `bard.on_room_change` — при загрузке не пользоваться ими для позиции (сбрасывают восстановленное состояние).
- Босса Моргарт в бою не сохранять (живой `HandSet`) — либо переспавнивать через `spawn_boss`.
- После восстановления ящиков/мехов обязательно `r.build()`.
- Сохранять только в `menu_mode == "pause"` (мир заморожен), а не во время симуляции.

**Рекомендуемая структура JSON-сейва** — в разделе 5.2 отчёта (версия, `run`/`loop`/`came_from`/`room`/`player_pos`/`progress`/`mobs`/`drops`/`turrets`/`containers`/`mechs`, секция `player` на каждого героя). Валидация id через `inventory.is_item`, `crafting.is_resource`, `sid in CFG["skills"]`.

Полный отчёт (640 строк, с точными `файл:строка`, сигнатурами и JSON-схемой) лежит в **`multiagent/out/audit_save.md`**.

RESULT_OK