Ты — агент-аналитик в проекте DEAD ROOMS (Python/Pygame-ce рогалик) в каталоге C:/Users/artem/Desktop/DEAD_ROOMS.
Задача: подготовить ПОЛНЫЙ аудит состояния игры для системы сохранений. Твой отчёт будут использовать 4 агента-исполнителя, которые напишут модули сохранения/загрузки/смены героя. Пиши отчёт на РУССКОМ, максимально конкретно: путь_к_файлу:строка, имена атрибутов, сигнатуры функций.

Составь отчёт из разделов:

## 1. Состояние забега (что сериализовать в файл сохранения)
- main.py: класс Game (~строка 529) — перечисли ВСЕ поля экземпляра, созданные в __init__ и new_game (~575), раздели на: «сохранять» / «временное» (fx, projs, warn_t, hud_drag и т.п.).
- maps.py: класс Campaign (~434) — поля loop/maps/came_from; как восстановить (get(), order, first).
- maps.py: класс GameMap — поля visited/cleared/spawned/locked/boss_spawned/mobs/corpses/drops/turrets/exits/lights. Что из этого сохранять и как восстанавливать (объекты создаются заново из CFG["map_defs"] через camp.get(mid)).
- Мобы в комнате: как создать заново (mob.py Mob(kind, x, y, scale, room=...)), какие поля моба сохранить (kind, x, y, scale, hp, state, face, dir?). За образец сериализации возьми multiplayer.py: HostSession.snapshot() (мобы/дропы/контейнеры/мехи/трупы) — выпиши точные форматы строк.
- Дропы: maps.Drop(x,y,wid) и crafting.ResourceDrop(x,y,rid) — оба лежат в r.drops (в multiplayer.py:739 это сериализуют, посмотри как).
- containers.py: containers.state(r) и функция восстановления у клиента (apply_world в multiplayer.py ~972) — как воссоздать ящики.
- mechs.py: mechs.state(r) — аналогично.
- crafting.py: турели (r.turrets) — живут до выхода из комнаты; реши, сохранять ли (можно НЕ сохранять, но обоснуй).
- Позиция героя в комнате: s.respawn, s.armed, s.pl.x/y, s.room.id — как восстановить через Game.go(mid, None) и place().

## 2. Состояние игрока, привязанное к герою (сохраняется ОТДЕЛЬНО на каждого героя забега)
main.py: класс Player (~69). Полный список «постоянных» полей героя: hp, maxhp, mana, level, xp, xp_next, skills, item_skills, skill_cooldowns, skill_index, slots, bag, equip, resources, last_weapon, goggles, hold_pool, hold_rest, char_id и т.д.
Проверь и опиши подсостояния:
- inventory.py: init(pl) (~162) — pl.bag, pl.equip, pl.resources; как сериализовать/восстановить (bag — список id или None; equip — слот->id; resources — id->кол-во).
- crossbow.py: что crossbow.init(pl) создаёт у pl (арбалеты, индексы снарядов, перезарядки) — перечисли атрибуты и как их восстановить.
- bard.py: что bard.init(pl) создаёт (ноты, усилители pl.amps) — что сохранять (усилители), что отбросить (играющая нота).
- clone.py: pl.clones — ВРЕМЕННОЕ (не сохранять, обоснуй).
- invisibility.py: pl.invis — ВРЕМЕННОЕ.
- status.py, hold_pool, skill_cast, channel — что из этого постоянное (hold_pool — да), что нет.
- Пассивные бонусы от экипировки: inventory.stat(pl, key) — пересчитываются из equip, отдельно не хранить (обоснуй).

## 3. Смена персонажа посреди забега
- core.py: apply_character(cid) (~111), _set_char (~126), CHAR = {"id": None} (~78), char_ids(), char_def(cid). Что mutate apply_character (CFG["character"]), что ещё нужно вызвать после него (clear_cache из anim.py И/ИЛИ inventory.py — main.py импортирует clear_cache из anim (~9) и в new_game вызывает apply_character(...); clear_cache()).
- characters.py: SETTINGS["last_character"] = cid; g.save_settings() (~117) — как выбор героя сохраняется в настройки.
- Чем опасна смена героя на живом Player: хитбокс (data/characters.json -> hitbox, pl.H0), spellcaster/crossbows/bard флаги создают разные стартовые слоты, crossbow.init/bard.init/inventory.init должны быть вызваны заново. Предложи безопасный сценарий: снапшот старого героя -> apply_character -> новый Player -> восстановить снапшот (если герой уже был в забеге) -> позиция = позиция старого героя -> pl.clones/atk/etc сбросить.

## 4. Точки интеграции в main.py (для главного агента, исполнители НЕ правят main.py!)
- Menu routing: key() (~806), menu_event() (~940), draw_menu() (~983), menu_action() (~886), menu_layout() (~903) — точные места, куда вставить режимы "saves"/"saves_char"/"swap".
- Меню паузы сейчас: options = ["continue","new","exit"] (в menu_event ~943 и draw_menu ~996, layout defaults в menu_layout ~907) — что заменить на 5 кнопок: ПРОДОЛЖИТЬ/ВЫБОР ПЕРСОНАЖА/СОХРАНИТЬСЯ/ЗАГРУЗИТЬ/ГЛАВНОЕ МЕНЮ.
- Клавиша Esc ставит s.menu_mode = "pause" (~888).
- multiplayer: s.net — в сетевой игре сохранения/смена героя отключить (найди все места, где поведение ветвится по s.net).
- F5 — перезагрузка данных (не трогать), K_r — рестарт.

## 5. Риски и рекомендации
- Что может сломаться при восстановлении (запертые двери при пустой комнате, боссы, circular imports, игровые клоны, hold-потоки).
- Рекомендуемая структура JSON-файла сохранения (версия, время, loop, room, heroes, camp).

Изучи файлы: main.py, maps.py, core.py, inventory.py, crossbow.py, bard.py, clone.py, invisibility.py, characters.py, multiplayer.py, containers.py, mechs.py, crafting.py, data/characters.json.
НЕ редактируй НИКАКИЕ файлы проекта — только читай. Твой финальный ответ = весь отчёт (он сохранится в multiagent/out/audit_save.md). Заверши строкой RESULT_OK.
