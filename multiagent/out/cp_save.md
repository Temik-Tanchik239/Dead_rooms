Готово. Итог по задаче **[cp_save]** — изменён только `save_io.py` (+67/−12), отчёт в `multiagent/out/cp_save.md`.

**Что сделано в `save_io.py`:**
1. **`snapshot_player`** — поле `"cp"` через хелпер `_cp_snapshot()`: `["<mid>", int(x), int(y)]` или `None` (нет атрибута/невалидно). Через `getattr(pl, "cp", None)` — работает и для фейковых объектов.
2. **`restore_player`** — валидный cp (3 элемента, `mid` есть в `CFG["map_defs"]`, координаты — числа) → `pl.cp = (str(mid), int(x), int(y))`; иначе `pl.cp = None`. Старые сейвы без поля не падают.
3. **`save(g, label=None, save_id=None)`** — заданный `save_id` → файл `saves/<save_id>.json` (нормализация через `_resolve_path`: `.json` отрезается, `../` → `ValueError`), существующий файл перезаписывается, meta возвращается как раньше.
4. **`autosave(g)`** — один слот `saves/autosave.json`, label «Чекпоинт · ДД.ММ.ГГГГ ЧЧ:ММ», перезапись; в сети `RuntimeError` унаследован от `save`.
5. **`list_saves`** — глоб `save_*.json` не матчит `autosave.json`, слот добавлен явно; сортировка `(time, mtime, num)` — новые первыми, тай-брейк по mtime, чтобы сейвы одной минуты не путались.
6. **Docstring** — описаны `"cp"` в heroes, слот autosave, cp в списке сохраняемого. **`VERSION = 1` не менялся.**

**Проверено headless (SDL dummy):** cp в `doc["heroes"][cid]["cp"]` (в т.ч. карта-«пустышка»); restore → `('env_7_0', 12, 20)`; несуществующая карта в cp → `None`; сейв без `cp` → `pl.cp is None` без падений; 7 вариантов мусорного cp → `None` в снапшоте; autosave — файл один при повторе, виден в `list_saves()` с именем «Чекпоинт · …»; перезапись по `save_id`; `"../escape"` → `ValueError`; в сети `save`/`autosave` → `RuntimeError`; `py_compile` OK; папка `saves/` после тестов **пуста** (0 файлов). `main.py`, `multiplayer.py`, `maps.py`, `checkpoint.py`, `map_editor.py` не тронуты.

RESULT_OK