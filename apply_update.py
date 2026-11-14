# -*- coding: utf-8 -*-
"""DEAD ROOMS — установка апдейта v3: «Мелкие детали» — декор с пиксельной точностью в редакторе карт и в игре.

Правки вносятся по СОДЕРЖИМОМУ файлов (а не по номерам строк), поэтому накладываются и на вашу локальную версию.
Каждый файл — всё или ничего. Перед изменением делается копия <файл>.bak_before_update. Повторный запуск безопасен.
Если какой-то файл не подошёл, скрипт предложит заменить его целиком (ваши правки в нём пропадут, копия останется).
Весь вывод дублируется в update_log.txt — пришлите его, если что-то пошло не так.
Запуск:  python apply_update.py [--full]   (--full — сразу заменять целиком те файлы, куда правки не легли)."""
import difflib, json, os, platform, py_compile, shutil, sys, tempfile, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd() if (Path.cwd() / "main.py").is_file() else HERE
LOG = []


def say(*parts):
    msg = " ".join(str(p) for p in parts)
    LOG.append(msg)
    try:
        print(msg)
    except UnicodeEncodeError:                       # консоль без Unicode — печатаем хоть как-то, лог полный
        print(msg.encode("ascii", "replace").decode("ascii"))


def save_log():
    try:
        (ROOT / "update_log.txt").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    except OSError:
        pass


def _split(old, new):
    """Делит правку на общий контекст до/после и изменённое ядро: (prefix, old_core, new_core, suffix) списками строк."""
    a, b = old.splitlines(True), new.splitlines(True)
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]: i += 1
    j = 0
    while j < len(a) - i and j < len(b) - i and a[len(a) - 1 - j] == b[len(b) - 1 - j]: j += 1
    return a[:i], a[i:len(a) - j], b[i:len(b) - j], a[len(a) - j:]


def _locate(text, old, new):
    """Единственное место для правки: с полным контекстом, затем с меньшим (по краям независимо) — так правка ложится,
    даже если рядом у вас локальные изменения. -> (старый_фрагмент, новый_фрагмент) или None."""
    pre, oc, nc, suf = _split(old, new)
    for total in range(len(pre) + len(suf), -1, -1):
        for hp in range(min(len(pre), total), -1, -1):
            ts = total - hp
            if ts > len(suf): continue
            before = pre[len(pre) - hp:] if hp else []
            after = suf[:ts]
            o = "".join(before + oc + after)
            if not o.strip() or (not oc and not (before or after)): continue
            if text.count(o) == 1:
                return o, "".join(before + nc + after)
    return None


def apply_hunks(text, hunks):
    """-> (новый_текст, [сообщения об ошибках], сколько_уже_применено, сколько_применено)"""
    errs, done, skipped = [], 0, 0
    for i, h in enumerate(hunks, 1):
        old, new, uniq = h[0], h[1], (h[2] if len(h) > 2 else False)
        _, oc, nc, _ = _split(old, new)
        core = "".join(nc)
        if new in text or (uniq and core in text):
            skipped += 1; continue                       # уже применено раньше
        if text.count(old) == 1:
            text = text.replace(old, new, 1); done += 1; continue
        hit = _locate(text, old, new)
        if hit:
            text = text.replace(hit[0], hit[1], 1); done += 1; continue
        first = next((l for l in (oc or old.splitlines(True)) if l.strip()), "…").strip()
        close = difflib.get_close_matches(first, [l.strip() for l in text.splitlines()], n=1, cutoff=0.5)
        errs.append(f"правка №{i}: место не найдено или в нём ваши локальные изменения.\n"
                    f"               ожидалась строка: {first[:110]!r}\n"
                    f"               в вашем файле похожа: {close[0][:110]!r}" if close else
                    f"правка №{i}: место не найдено или в нём ваши локальные изменения.\n"
                    f"               ожидалась строка: {first[:110]!r}")
    return text, errs, skipped, done


def read_text(path):
    """-> (текст с LF, crlf?, bom?). Понимает BOM и CRLF; не-UTF-8 файл — понятная ошибка."""
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    if bom: raw = raw[3:]
    text = raw.decode("utf-8")
    return text.replace("\r\n", "\n"), "\r\n" in text, bom


def write_text(path, text, crlf, bom):
    data = (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def check_valid(rel, text):
    """None, если текст годится; иначе описание проблемы (не оставляем сломанный Python/JSON)."""
    if rel.endswith(".py"):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8", newline="") as tf:
                tf.write(text); tmp = tf.name
            py_compile.compile(tmp, cfile=tmp + "c", doraise=True)
        except py_compile.PyCompileError as e:
            return f"некорректный Python: {e.msg}"
        finally:
            for t in (tmp, (tmp + "c") if tmp else None):
                if t and os.path.exists(t):
                    try: os.unlink(t)
                    except OSError: pass
    elif rel.endswith(".json"):
        try: json.loads(text)
        except ValueError as e: return f"некорректный JSON: {e}"
    return None


def main():
    say("DEAD ROOMS — установка апдейта v3")
    say(f"Python {platform.python_version()} · {platform.system()} · папка проекта: {ROOT}")
    if not (ROOT / "main.py").is_file():
        say("ОШИБКА: не нашёл main.py. Положите содержимое архива в папку проекта (где main.py) и запустите оттуда.")
        return 1
    try:
        data = json.loads((HERE / "update_data.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        say(f"ОШИБКА: не прочитался update_data.json рядом со скриптом ({e}). Распакуйте архив целиком.")
        return 1
    force = "--full" in sys.argv
    say("")
    failed = []                                                    # (rel, причина, обязательный)
    for rel, spec in data.items():
        path = ROOT / rel
        try:
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="") as f: f.write(spec["full"])
                say(f"[создан]   {rel}")
                continue
            text, crlf, bom = read_text(path)
            new_text, errs, skipped, done = apply_hunks(text, spec["hunks"])
            problem = None
            if errs:
                problem = "правки не легли:\n            " + "\n            ".join(errs)
            elif done:
                bad = check_valid(rel, new_text)
                if bad: problem = f"после правки получился {bad}"
            if problem:
                say(f"[НЕ ПОДОШЁЛ] {rel}: файл НЕ изменён\n            {problem}")
                failed.append((rel, problem, spec["required"]))
                continue
            if done == 0:
                say(f"[уже есть] {rel}"); continue
            bak = path.with_name(path.name + ".bak_before_update")
            if not bak.exists(): shutil.copy2(path, bak)
            write_text(path, new_text, crlf, bom)
            say(f"[обновлён] {rel}  (правок: {done}{', уже были: ' + str(skipped) if skipped else ''})")
        except Exception:
            say(f"[ОШИБКА]   {rel}: непредвиденная ошибка\n" + traceback.format_exc())
            failed.append((rel, "непредвиденная ошибка (см. выше)", spec["required"]))
    if failed:
        say("")
        say("Не обновились: " + ", ".join(r for r, _, _ in failed) + ". Эти файлы не тронуты, остальное обновлено.")
        answer = "y" if force else ""
        if not force and sys.stdin and sys.stdin.isatty():
            say("Можно заменить их ПОЛНОСТЬЮ версиями из апдейта. Ваши локальные правки В ЭТИХ ФАЙЛАХ пропадут")
            say("(копия <файл>.bak_before_update останется рядом, её можно вернуть).")
            try: answer = input("Заменить целиком? [y/N]: ").strip().lower()
            except EOFError: answer = ""
            LOG.append(f"ответ: {answer!r}")
        if answer in ("y", "yes", "д", "да"):
            still = []
            for rel, _, req in failed:
                path = ROOT / rel
                try:
                    if path.is_file():
                        bak = path.with_name(path.name + ".bak_before_update")
                        if not bak.exists(): shutil.copy2(path, bak)
                        _, crlf, bom = read_text(path)
                    else:
                        crlf = bom = False
                    full = data[rel]["full"]
                    bad = check_valid(rel, full)
                    if bad: raise ValueError(bad)
                    write_text(path, full, crlf, bom)
                    say(f"[заменён целиком] {rel}")
                except Exception as e:
                    say(f"[ОШИБКА]   {rel}: не удалось заменить ({e})"); still.append(rel)
            failed = [f for f in failed if f[0] in still]
    say("")
    if failed:
        say("ИТОГ: апдейт установлен не полностью. Пришлите файл update_log.txt (лежит в папке проекта).")
        return 3
    say("ГОТОВО. Игра: F5 (или перезапуск). Редактор: launch_map_editor.bat — вкладка «Карты», внизу панель «Мелкие детали».")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        say("НЕПРЕДВИДЕННАЯ ОШИБКА УСТАНОВЩИКА:\n" + traceback.format_exc()); code = 1
    save_log()
    sys.exit(code)
