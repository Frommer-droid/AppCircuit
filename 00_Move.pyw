# -*- coding: utf-8 -*-
"""
Шаблон переноса свежей portable-папки приложения в целевую директорию.

Как адаптировать:
1. Заменить APP_NAME на имя папки релиза и exe.
2. Заменить DESTINATION_PARENT на базовую папку portable-приложений.

Скрипт завершает только процесс, запущенный из целевой папки, затем заменяет
целевую папку свежей папкой из корня проекта.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
import tkinter as tk
from pathlib import Path


APP_NAME = "AppCircuit"
DESTINATION_PARENT = Path(r"D:\Portable_soft")
LEGACY_APP_NAMES = ("Job App Off On",)
PRESERVE_FILES = ("settings.json",)


def remove_readonly(func, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as exc:
        print(f"Не удалось удалить {path}: {exc}")


def show_popup(message: str, is_error: bool = False) -> None:
    if os.environ.get("APPCIRCUIT_RELEASE_NONINTERACTIVE") == "1":
        print(message)
        return
    try:
        root = tk.Tk()
        root.attributes("-topmost", True)
        root.title("Ошибка" if is_error else "Готово")
        bg_color = "#ffcccc" if is_error else "#e6ffe6"
        root.configure(bg=bg_color)
        width = 560 if is_error else 420
        height = 220 if is_error else 140
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        label = tk.Label(
            root,
            text=message,
            font=("Arial", 11),
            bg=bg_color,
            wraplength=width - 30,
        )
        label.pack(expand=True, padx=18, pady=16)
        button = tk.Button(root, text="Закрыть", command=root.destroy)
        button.pack(pady=(0, 12))
        root.mainloop()
    except Exception:
        print(message)


def ensure_safe_target(target: Path, parent: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_target = target.resolve() if target.exists() else target.absolute()
    if resolved_target == resolved_parent:
        raise RuntimeError("Целевая папка совпадает с родительской папкой.")
    try:
        resolved_target.relative_to(resolved_parent)
    except ValueError as exc:
        raise RuntimeError(
            f"Небезопасный путь удаления/копирования: {resolved_target}"
        ) from exc


def kill_process_by_path(process_name: str, path_filter: Path) -> None:
    process_name_no_ext = process_name.replace(".exe", "")
    escaped_path = str(path_filter).replace("'", "''")
    ps_command = (
        "powershell -NoProfile -ExecutionPolicy Bypass -Command "
        f"\"$target = [System.IO.Path]::GetFullPath('{escaped_path}'); "
        "if (-not $target.EndsWith([System.IO.Path]::DirectorySeparatorChar)) "
        "{ $target += [System.IO.Path]::DirectorySeparatorChar }; "
        f"Get-Process -Name '{process_name_no_ext}' -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -and "
        "([System.IO.Path]::GetFullPath($_.Path)).StartsWith($target, "
        "[System.StringComparison]::OrdinalIgnoreCase) } | "
        "Stop-Process -Force\""
    )
    for _ in range(3):
        subprocess.run(
            ps_command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)


def preserved_runtime_files(
    target_folder: Path,
    legacy_folders: tuple[Path, ...] = (),
) -> dict[str, bytes]:
    preserved: dict[str, bytes] = {}
    for folder in (target_folder, *legacy_folders):
        for filename in PRESERVE_FILES:
            source = folder / filename
            if filename not in preserved and source.is_file():
                preserved[filename] = source.read_bytes()
    return preserved


def replace_portable_folder(
    source_folder: Path,
    target_folder: Path,
    preserved: dict[str, bytes],
) -> None:
    if target_folder.exists():
        shutil.rmtree(target_folder, onerror=remove_readonly)
        print(f"[OK] Удалена старая папка: {target_folder}")

    shutil.copytree(source_folder, target_folder)
    for filename, content in preserved.items():
        (target_folder / filename).write_bytes(content)
    print(f"[OK] Скопировано: {source_folder} -> {target_folder}")


def main() -> int:
    project_root = Path(__file__).resolve().parent
    source_folder = project_root / APP_NAME
    target_folder = DESTINATION_PARENT / APP_NAME
    legacy_folders = tuple(DESTINATION_PARENT / name for name in LEGACY_APP_NAMES)
    exe_name = f"{APP_NAME}.exe"

    if not source_folder.is_dir():
        show_popup(f"Исходная папка не найдена:\n{source_folder}\n\nСначала выполните сборку.", True)
        return 1

    DESTINATION_PARENT.mkdir(parents=True, exist_ok=True)
    ensure_safe_target(target_folder, DESTINATION_PARENT)

    kill_process_by_path(exe_name, target_folder)
    time.sleep(1)
    preserved = preserved_runtime_files(target_folder, legacy_folders)
    replace_portable_folder(source_folder, target_folder, preserved)

    show_popup(f"Portable-папка обновлена:\n{target_folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
