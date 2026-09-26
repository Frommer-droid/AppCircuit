# -*- coding: utf-8 -*-
"""
Шаблон создания Windows-установщика через Inno Setup.

Как адаптировать:
1. Заменить APP_NAME, APP_PUBLISHER и APP_ID.
2. Проверить KEEP_FOLDERS: обычно достаточно ("_internal",).
3. Добавить нужные обязательные файлы в REQUIRED_RELEASE_FILES.
4. Проверить INSTALLER_OUTPUT_DIR и ISCC_CANDIDATE_PATHS.
5. Сначала собрать приложение и выполнить Build_Tools/post_build.py.
6. Запустить этот файл из корня проекта.

Шаблон содержит только упаковку готовой папки приложения в Windows-установщик.
"""

from __future__ import annotations

import os
import shutil
import string
import stat
import subprocess
import tempfile
import time
import tkinter as tk
from pathlib import Path


APP_NAME = "AppCircuit"
APP_PUBLISHER = "Frommer-droid"

# Для каждого приложения сгенерировать свой GUID.
# Формат для Inno Setup: "{{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"
APP_ID = "{{5B3C13FC-82A4-4F36-A14D-C16FD5180FD6}}"

KEEP_FOLDERS = ("_internal",)
REQUIRED_RELEASE_FILES = (
    "VERSION",
    "logo.ico",
    "RUNTIME_MANIFEST.json",
)
RUNTIME_NOISE_FILES = (
    "settings.json",
    "launch_cache.json",
)

def _desktop_from_registry() -> Path | None:
    """Путь рабочего стола из HKCU User Shell Folders — учитывает перенос
    пользователем на нестандартный диск/каталог."""
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            value, _type = winreg.QueryValueEx(handle, "Desktop")
        expanded = os.path.expandvars(value)
        if expanded:
            return Path(expanded)
    except Exception:
        pass
    return None


def _desktop_from_known_folder() -> Path | None:
    """FOLDERID_Desktop через SHGetKnownFolderPath (современный API)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
        folderid_desktop = GUID(
            0xB4BFCC3A, 0xDB2C, 0x424C,
            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
        )
        out_ptr = ctypes.c_wchar_p()
        hresult = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(folderid_desktop), 0, None, ctypes.byref(out_ptr)
        )
        try:
            if hresult == 0 and out_ptr.value:
                return Path(out_ptr.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out_ptr)
    except Exception:
        pass
    return None


def _desktop_from_shgetfolder() -> Path | None:
    """CSIDL_DESKTOPDIRECTORY через устаревший SHGetFolderPathW."""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer)
        if result == 0 and buffer.value:
            return Path(buffer.value)
    except Exception:
        pass
    return None


def resolve_desktop_dir() -> Path:
    """Настоящий рабочий стол пользователя, а не дефолт %USERPROFILE%\\Desktop.

    Источники по приоритету: явный env APPCIRCUIT_DESKTOP_DIR → реестр User Shell
    Folders (куда записан перенос стола) → SHGetKnownFolderPath → устаревший
    SHGetFolderPathW → и лишь как последний вариант ~/Desktop.
    """
    override = os.environ.get("APPCIRCUIT_DESKTOP_DIR", "").strip()
    if override:
        return Path(override)
    for resolver in (
        _desktop_from_registry,
        _desktop_from_known_folder,
        _desktop_from_shgetfolder,
    ):
        candidate = resolver()
        if candidate is not None:
            return candidate
    return Path.home() / "Desktop"


def iter_fixed_drives() -> list[Path]:
    try:
        import ctypes

        drive_type_fixed = 3
        drives: list[Path] = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(root) == drive_type_fixed:
                drives.append(Path(root))
        if drives:
            return drives
    except Exception:
        pass
    return [Path(r"C:\\")]


def resolve_default_install_base_dir() -> Path:
    fixed_drives = iter_fixed_drives()

    for drive in fixed_drives:
        if str(drive).upper().startswith("D:"):
            return drive / "Apps"

    for drive in fixed_drives:
        if not str(drive).upper().startswith("C:"):
            return drive / "Apps"

    return Path(r"C:\Apps")


INSTALLER_OUTPUT_DIR = resolve_desktop_dir()
DEFAULT_INSTALL_BASE_DIR = resolve_default_install_base_dir()
PRIVILEGES_REQUIRED = "admin"

ISCC_CANDIDATE_PATHS = (
    str(Path(__file__).resolve().parent.parent / "tools" / "Inno Setup 6" / "ISCC.exe"),
    os.environ.get("INNO_SETUP_ISCC", ""),
    shutil.which("ISCC.exe") or "",
    str(
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Inno Setup 6"
        / "ISCC.exe"
    ),
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
)


def find_iscc_path() -> str:
    for path in ISCC_CANDIDATE_PATHS:
        if path and os.path.exists(path):
            return path
    return ""


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


def should_remove_runtime_file(filename: str) -> bool:
    name_lower = filename.lower()
    return (
        name_lower in RUNTIME_NOISE_FILES
        or name_lower.endswith(".log")
        or ".log." in name_lower
    )


def get_missing_release_items(source_dir: Path, exe_name: str) -> list[str]:
    missing: list[str] = []
    for filename in (*REQUIRED_RELEASE_FILES, exe_name):
        if not (source_dir / filename).is_file():
            missing.append(filename)
    for folder in KEEP_FOLDERS:
        if not (source_dir / folder).is_dir():
            missing.append(folder + "/")
    return missing


def prepare_work_dir(source_dir: Path, work_dir: Path) -> None:
    if work_dir.exists():
        shutil.rmtree(work_dir, onerror=remove_readonly)
    shutil.copytree(source_dir, work_dir)

    keep_folders_lower = {folder.lower() for folder in KEEP_FOLDERS}
    for item in work_dir.iterdir():
        if item.is_dir() and item.name.lower() not in keep_folders_lower:
            shutil.rmtree(item, onerror=remove_readonly)
            print(f"Удалена лишняя папка: {item.name}")
        elif item.is_file() and should_remove_runtime_file(item.name):
            item.unlink(missing_ok=True)
            print(f"Удален runtime-файл: {item.name}")

    for root, _dirs, files in os.walk(work_dir):
        for filename in files:
            name_lower = filename.lower()
            if name_lower.endswith(".log") or ".log." in name_lower:
                Path(root, filename).unlink(missing_ok=True)


def read_version(project_root: Path) -> str:
    version_path = project_root / "VERSION"
    if version_path.is_file():
        version = version_path.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "0.0.0"


def build_iss_script(
    *,
    app_name: str,
    app_id: str,
    app_publisher: str,
    version: str,
    exe_name: str,
    work_dir: Path,
    output_dir: Path,
    default_install_dir: Path,
    setup_icon_file: Path | None,
) -> str:
    setup_icon_line = f'SetupIconFile="{setup_icon_file}"' if setup_icon_file else ""
    return f"""; Автоматически сгенерированный Inno Setup script.

#define MyAppName "{app_name}"
#define MyAppVersion "{version}"
#define MyAppPublisher "{app_publisher}"
#define MyAppExeName "{exe_name}"

[Setup]
AppId={app_id}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
DefaultDirName="{default_install_dir}"
UsePreviousAppDir=no
DefaultGroupName={{#MyAppName}}
DisableProgramGroupPage=yes
UninstallDisplayIcon="{{app}}\\{{#MyAppExeName}}"
OutputDir="{output_dir}"
OutputBaseFilename={{#MyAppName}}_v{{#MyAppVersion}}_Setup
{setup_icon_line}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired={PRIVILEGES_REQUIRED}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={{#MyAppVersion}}.0
VersionInfoCompany={{#MyAppPublisher}}
VersionInfoDescription={{#MyAppName}} Setup
VersionInfoProductName={{#MyAppName}}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительные значки:"; Flags: checkedonce

[Files]
Source: "{work_dir}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\logo.ico"
Name: "{{group}}\\Удалить {{#MyAppName}}"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\logo.ico"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "Запустить {{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM {{#MyAppExeName}}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}"
"""


def main() -> int:
    project_root = Path(__file__).resolve().parent
    source_dir = project_root / APP_NAME
    exe_name = f"{APP_NAME}.exe"
    iscc_path = find_iscc_path()

    if not iscc_path:
        show_popup("Не найден ISCC.exe. Установите Inno Setup 6 или задайте INNO_SETUP_ISCC.", True)
        return 1

    if not source_dir.is_dir():
        show_popup(f"Не найдена папка релиза:\n{source_dir}\n\nСначала выполните сборку.", True)
        return 1

    missing = get_missing_release_items(source_dir, exe_name)
    if missing:
        show_popup("Папка релиза неполная:\n" + "\n".join(f"- {item}" for item in missing), True)
        return 1

    temp_root = Path(tempfile.mkdtemp(prefix="appcircuit-installer-"))
    work_dir = temp_root / APP_NAME
    kill_process_by_path(exe_name, source_dir)
    prepare_work_dir(source_dir, work_dir)

    version = read_version(project_root)
    setup_icon_file = work_dir / "logo.ico" if (work_dir / "logo.ico").is_file() else None
    iss_content = build_iss_script(
        app_name=APP_NAME,
        app_id=APP_ID,
        app_publisher=APP_PUBLISHER,
        version=version,
        exe_name=exe_name,
        work_dir=work_dir,
        output_dir=Path(INSTALLER_OUTPUT_DIR),
        default_install_dir=DEFAULT_INSTALL_BASE_DIR / APP_NAME,
        setup_icon_file=setup_icon_file,
    )

    iss_path = Path(tempfile.gettempdir()) / f"{APP_NAME}_installer_temp.iss"
    iss_path.write_text(iss_content, encoding="utf-8-sig")

    try:
        subprocess.run([iscc_path, str(iss_path)], check=True)
    except subprocess.CalledProcessError as exc:
        show_popup(f"Ошибка Inno Setup:\n{exc}", True)
        return 1
    finally:
        iss_path.unlink(missing_ok=True)
        if work_dir.exists():
            shutil.rmtree(work_dir, onerror=remove_readonly)
        if temp_root.exists():
            shutil.rmtree(temp_root, onerror=remove_readonly)

    show_popup(f"Установщик готов:\n{APP_NAME}_v{version}_Setup.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
