Ты — pi-агент в проекте DEAD ROOMS (Python/Pygame-ce рогалик, каталог C:/Users/artem/Desktop/DEAD_ROOMS).
ЗАДАЧА: доработай save_io.py под систему чекпоинтов: точка возрождения героя в сейве + слот автосохранения.

СНАЧАЛА изучи save_io.py целиком (он небольшой, ~520 строк): snapshot_player (~280), restore_player (~317), save (~395), restore (~426), list_saves (~512), _read, _path. Посмотри main.py Player (~73) и swap.py — snapshot_player зовут и оттуда.

ЧТО СДЕЛАТЬ:
1. snapshot_player: добавь поле
       "cp": [mid, x, y] или None
   — точка возрождения героя: getattr(pl, "cp", None); mid — строка id карты, x/y — целые. None, если атрибута нет или он невалиден.
2. restore_player: если в снапшоте есть валидный "cp" (список из 3 элементов, mid — существующая карта в CFG["map_defs"], x/y числа) — установи pl.cp = (str(mid), int(x), int(y)); иначе pl.cp = None. Старые сейвы без поля не должны падать.
3. save(g, label=None, save_id=None): новый параметр save_id — если задан (после _safe-нормализации имени, как в _read: без "/" "\\" ".json"), файл называется <save_id>.json вместо save_<N>.json; если файл с таким id уже есть — ПЕРЕЗАПИСАТЬ. Возврат meta как раньше (id = нормализованное имя).
4. Добавь функцию:
       def autosave(g): """Автосохранение чекпоинта: один слот saves/autosave.json, перезаписывается.""" 
   — вызывает save(g, label=f"Чекпоинт · {дата %d.%m.%Y %H:%M}", save_id="autosave"); в сетевой игре — RuntimeError (унаследуется от save, он уже проверяет g.net).
5. list_saves: ничего менять не надо, autosave.json подхватится сам (id "autosave"). Убедись, что сортировка не сломается (autosave может быть старее/новее — новые первыми по времени создания).
6. Обнови docstring формата файла в начале модуля: добавь строки про "cp" у героев и слот autosave.
7. ВЕРСИЮ ФОРМАТА (VERSION) НЕ МЕНЯЙ — поле "cp" опциональное, старые сейвы читаются как есть.

ПРОВЕРКА (headless): SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe:
- создать main.Game, g.new_game(); g.pl.cp = ("какой-то_map", 100, 64); save_io.save(g) → в doc["heroes"][cid]["cp"] лежит cp;
- save_io.autosave(g) → появился saves/autosave.json, list_saves() его видит; повторный autosave НЕ создаёт новый файл (количество файлов не растёт);
- restore → pl.cp восстановился; старый сейв без cp → pl.cp is None.
- ВСЕ ТЕСТОВЫЕ СЕЙВЫ из папки saves/ УДАЛИ после проверки (папка должна остаться пустой).
- py_compile save_io.py.

НЕ редактируй: main.py, multiplayer.py, maps.py, checkpoint.py, map_editor.py.
Отчёт: multiagent/out/cp_save.md — что изменено, контракт, как протестировано.
