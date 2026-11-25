Задача [mp_rooms] завершена. Итог:

## Состояние
Рефакторинг `multiplayer.py` — независимое исследование мира — выполнен полностью и проверен по всем 10 пунктам дизайна (файл 1532 строки, diff +208/−86 относительно базы 1410):

1. **`p.room_id`** — у всех игроков, назначается в `go` (старт: карта хоста) / `go_player` / `join_game`, на клиенте — из поля `"rm"` снимка.
2. **`s.sims = {mid: SimpleNamespace(room, projs, armed, room_armed, fx=core.FX(), respawn)}`** — мир на каждую комнату; `sync_host_room()` держит `g.room/g.projs/g.fx` на комнате хоста каждый кадр.
3. **`step()`** разделён: общая часть (feed_local, game_over, bard.PLAYERS) + группировка по `p.room_id` → `step_room(sim, players, dt)`; пустые комнаты не симулируются; пули/контейнеры/мехи/шипы/выходы/замки — per-room.
4. **Выходы индивидуальные**: `take_exit(p, z)` → `go_player(p, mid, via)` — `came_from`, `arrival`, `place` (копия `Game.place`, `p.tp += 1`), растворение клонов, сброс `channel/hold`; END → `g.done` для всех.
5. Мобы/опыт/босс/зачистка/замки — только игроки своей комнаты.
6. `respawn_player` — якорь из живых своей комнаты, иначе `sim.respawn` его комнаты.
7. **`snapshot_for(room_id)`** — персональный снимок (`"room"`, `"rm"` у каждого игрока, fx/mobs/drops/ct/mc/projs/cls — только комнаты); `update()` шлёт каждому conn его снимок, хосту — нет.
8. Клиент: буфер очищается при смене `"room"`; `apply_world` переключает `g.room` **до** `predict`; `tp`-перестановка в `apply_self`; `apply_mobs` кладёт мобов в комнату снимка.
9. `draw_players` — по комнате; `draw_overlay` — все игроки, `☠ ` вместо `✝ `, строка о поднятии убрана; `clone.view_of` обёрнут фильтром по комнате.
10. downed/revive сохранены как были (задел для [mp_death]); `main.py` не редактировался.

## Проверки
- `py_compile` — OK.
- `multiagent/out/mp_rooms_test.py` (headless, SDL dummy, настоящий `main.Game` + `FakeHost`, **9 секций**, включая новую клиентскую: комната из снимка → `g.room` до `predict` → `tp`-перестановка → `apply_mobs`) — **MP_ROOMS_TEST_OK**.
- Мусора тест не оставляет (проверено по `git status`, `saves/` пуст).

## Отчёт
`multiagent/out/mp_rooms.md` — новая структура, полный список полей снимка, методика тестов и единственная точная правка для main.py (строка 1184: фильтр `lit` по `room_id` для `lighting.apply` — вносит главный агент).

RESULT_OK