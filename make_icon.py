"""Готовит иконку для EXE: assets/app/icon.ico (если есть) или собирает .ico из assets/app/icon.png.

Запускается из build_exe.bat перед PyInstaller; результат — build_icon/DEAD_ROOMS.ico (его берёт --icon).
Нет ни icon.ico, ни icon.png — файл не создаётся, и EXE получает стандартную иконку.
Нужен только pygame (он уже в зависимостях проекта).
"""
import os, shutil, struct, sys, tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "assets" / "app"
OUT = ROOT / "build_icon" / "DEAD_ROOMS.ico"
SIZES = (256, 128, 64, 48, 32, 16)


def build_ico(blobs):
    """blobs — [(размер, байты PNG)]. ICO с PNG-кадрами (формат поддерживает Windows Vista и новее)."""
    head = struct.pack("<HHH", 0, 1, len(blobs)); offset = 6 + 16 * len(blobs); entries = b""; data = b""
    for size, png in blobs:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return head + entries + data


def png_bytes(surface):
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "i.png"; pygame.image.save(surface, str(f)); return f.read_bytes()


def square(img):
    """Квадратный холст с прозрачными полями: иконка не искажается, даже если PNG не квадратный."""
    w, h = img.get_size(); n = max(w, h)
    out = pygame.Surface((n, n), pygame.SRCALPHA); out.blit(img, ((n - w) // 2, (n - h) // 2)); return out


def main():
    OUT.parent.mkdir(exist_ok=True)
    ico, png = SRC_DIR / "icon.ico", SRC_DIR / "icon.png"
    if ico.is_file():
        shutil.copyfile(ico, OUT); print("иконка EXE: assets/app/icon.ico"); return 0
    if not png.is_file():
        OUT.unlink(missing_ok=True); print("иконка EXE: нет assets/app/icon.png — будет стандартная"); return 0
    img = square(pygame.image.load(str(png)))
    if min(img.get_size()) < 16: print("ОШИБКА: icon.png меньше 16x16"); return 1
    blobs = []
    for size in SIZES:
        if size > img.get_width() and size != 16: continue      # маленький исходник не растягиваем до 256
        blobs.append((size, png_bytes(pygame.transform.smoothscale(img, (size, size)))))
    OUT.write_bytes(build_ico(blobs)); print("иконка EXE: собрана из assets/app/icon.png, размеры:", [b[0] for b in blobs]); return 0


if __name__ == "__main__":
    sys.exit(main())
