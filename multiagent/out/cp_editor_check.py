# -*- coding: utf-8 -*-
"""Проверка кисти «Чекпоинт» (O) в редакторе и в игре. Запуск: ./.venv/Scripts/python.exe multiagent/out/cp_editor_check.py"""
import os, sys, io, json, hashlib
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
fails = []
def ok(cond, msg):
    print(("  OK  " if cond else "  FAIL") + " " + msg)
    if not cond: fails.append(msg)

# ---------- 1. Инварианты редактора ----------
print("== map_editor.py: константы кисти ==")
import map_editor as me

names = [ch for ch, _, _ in me.PALETTE]
ok("O" in names, f"PALETTE содержит 'O' (всего кистей: {len(me.PALETTE)})")
i = names.index("O")
ok(names[i - 1] == "%", "O стоит после источников света (после '%')")
ok(names[i + 1] == "W", "O стоит перед ресурсами (перед 'W')")
ok(me.PALETTE[i][1] == "Чекпоинт", "подпись кисти — «Чекпоинт»")
ok(me.PALETTE[i][2] == {"type": "empty", "checkpoint": True}, "определение = {'type': 'empty', 'checkpoint': True}")
ok("O" in me.GLOBAL_SYMBOLS, "GLOBAL_SYMBOLS содержит 'O' (не копируется в легенду карты)")
ok(me.LEGEND.get("O") == {"type": "empty", "checkpoint": True}, f"LEGEND['O'] = {me.LEGEND.get('O')}")
ok(me.COLORS.get("O") == "#6fd2ff", f"COLORS['O'] = {me.COLORS.get('O')}")
ok(len(names) == len(set(names)), "в PALETTE нет дубликатов символов")
ok(not (set(names) & set("АБВ")) and not set(names) & set(me.SYMBOL_POOL),
   "символы палитры не пересекаются с пулом символов своего света")

# ---------- 2. Логика легенды save_map (репликация строк 911-918) ----------
print("== save_map: 'O' попадает в rows, но НЕ в легенду карты ==")
rows = [list("....") for _ in range(4)]
rows[1][2] = "O"; rows[2][2] = "#"
data = {"legend": {"#": {"type": "wall"}}}   # как будто карта уже имела легенду
used = {ch for row in rows for ch in row}
legend = dict(data.get("legend", {}))
for ch, _, definition in me.PALETTE:
    if ch in used and ch not in me.GLOBAL_SYMBOLS:
        legend[ch] = definition
data["legend"] = legend
ok("O" in "".join("".join(r) for r in rows), "символ O остаётся в rows")
ok("O" not in data["legend"], f"'O' НЕ пишется в легенду карты (legend={data['legend']})")
ok("#" in data["legend"], "неглобальные символы по-прежнему пишутся в легенду")

# ---------- 3. Игра читает карту с 'O' ----------
print("== игра: карта с 'O' в rows ==")
import core, maps, checkpoint

test_rows = ["#" * 10] + ["#........#"] * 4 + ["#....O...#", "#........#", "##########"]
def build(mid, legend):
    m = {"name": "test", "rows": test_rows, "legend": legend}
    (core.DATA / "maps" / f"{mid}.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

before_hash = hashlib.sha256((core.DATA / "maps.json").read_bytes()).hexdigest()
order_before = json.loads((core.DATA / "maps.json").read_text(encoding="utf-8")).get("order", [])

# 3а) _test_cp.json (файл с '_' игра не читает — проверяем подстановкой в map_defs, как это сделал бы reload_data)
build("_test_cp", {})   # легенда карты БЕЗ 'O' — должен резолвиться из глобальной
core.reload_data()
core.CFG["map_defs"]["_test_cp"] = json.loads((core.DATA / "maps" / "_test_cp.json").read_text(encoding="utf-8"))
warns = [w for w in maps.check() if "_test_cp" in w]
ok(not warns, f"maps.check() для _test_cp без замечаний (легенда 'O' из maps.json): {warns or 'чисто'}")
lg = maps.legend_of(core.CFG["map_defs"]["_test_cp"])
ok(lg.get("O", {}).get("checkpoint") is True and lg["O"]["type"] == "empty",
   f"maps.legend_of резолвит 'O' из глобальной легенды: {lg.get('O')}")
ok("O" in maps.PHYS or lg["O"]["type"] in maps.PHYS, f"type 'empty' есть в maps.PHYS")
cp_file = core.DATA / "maps" / "_test_cp.json"

# 3б) zztest_cp.json — имя без '_': настоящий путь загрузки игры (reload_data сканирует каталог)
build("zztest_cp", {})
core.reload_data()
ok("zztest_cp" in core.CFG["map_defs"], "reload_data подхватил карту zztest_cp из каталога")
warns = [w for w in maps.check() if "zztest_cp" in w]
ok(not warns, f"maps.check() для zztest_cp без замечаний: {warns or 'чисто'}")
room = maps.GameMap("zztest_cp")
cps = checkpoint.collect(room)
ok(bool(cps), f"checkpoint.collect нашёл кристалл: {cps}")
T = core.T
cc, cr = int(cps[0]["rect"].x // T), int(cps[0]["rect"].y // T)
ok(room.g[cr][cc] != "#", f"клетка чекпоинта физически пустая (g[{cr}][{cc}]={room.g[cr][cc]!r})")
ok(room.checkpoints == cps, "GameMap.__init__ собрал r.checkpoints")

# ---------- 4. Уборка ----------
cp_file.unlink()
(core.DATA / "maps" / "zztest_cp.json").unlink()
core.reload_data()
ok(not cp_file.exists() and not (core.DATA / "maps" / "zztest_cp.json").exists(), "временные карты удалены")
after_hash = hashlib.sha256((core.DATA / "maps.json").read_bytes()).hexdigest()
ok(before_hash == after_hash, "data/maps.json не изменился (хэш до/после)")
order_after = json.loads((core.DATA / "maps.json").read_text(encoding="utf-8")).get("order", [])
ok(order_before == order_after and "zztest_cp" not in order_after and "_test_cp" not in order_after,
   "в order карт нет тестовых карт")
warns = [w for w in maps.check() if "zztest_cp" in w or "_test_cp" in w]
ok(not warns, f"после уборки maps.check() не упоминает тестовые карты: {warns or 'чисто'}")

print()
print("ИТОГ:", "ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if not fails else f"ПРОВАЛЕНО: {fails}")
sys.exit(1 if fails else 0)
