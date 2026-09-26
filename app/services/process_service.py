from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from app.models import ApplicationEntry

_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_NO_MORE_FILES = 18
_MAX_EXECUTABLE_PATH = 32768


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


@dataclass(slots=True)
class ActionReport:
    action: str
    succeeded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = [f"успешно: {len(self.succeeded)}"]
        if self.skipped:
            parts.append(f"пропущено: {len(self.skipped)}")
        if self.failed:
            parts.append(f"ошибок: {len(self.failed)}")
        return f"{self.action}: " + ", ".join(parts)


class ProcessService:
    def open_files(self, files: list[ApplicationEntry]) -> ActionReport:
        report = ActionReport("Открытие")
        for item in files:
            path = Path(item.path)
            if not path.is_file():
                report.failed.append(f"{item.name}: файл не найден")
                continue
            try:
                opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
            except OSError as exc:
                report.failed.append(f"{item.name}: {exc}")
                continue
            if opened:
                report.succeeded.append(item.name)
            else:
                report.failed.append(f"{item.name}: не удалось открыть файл")
        return report

    def launch(self, applications: list[ApplicationEntry]) -> ActionReport:
        report = ActionReport("Запуск")
        launchable: list[tuple[ApplicationEntry, Path]] = []
        for application in applications:
            executable = Path(application.path)
            if not executable.is_file():
                report.failed.append(f"{application.name}: файл не найден")
                continue
            launchable.append((application, executable))

        if not launchable:
            return report

        try:
            running_processes = self._running_process_ids_by_path()
        except OSError as exc:
            for application, _executable in launchable:
                report.failed.append(
                    f"{application.name}: не удалось проверить запущенные процессы: {exc}"
                )
            return report

        for application, executable in launchable:
            normalized_path = self._normalize_executable_path(executable)
            if normalized_path in running_processes:
                report.skipped.append(application.name)
                continue
            try:
                subprocess.Popen(
                    [str(executable)],
                    cwd=str(executable.parent),
                    close_fds=True,
                )
                report.succeeded.append(application.name)
                running_processes[normalized_path] = set()
            except OSError as exc:
                report.failed.append(f"{application.name}: {exc}")
        return report

    @staticmethod
    def _normalize_executable_path(path: str | Path) -> str:
        return str(Path(path).resolve(strict=False)).casefold()

    @staticmethod
    def _running_process_ids_by_path() -> dict[str, set[int]]:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_snapshot = kernel32.CreateToolhelp32Snapshot
        create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        create_snapshot.restype = wintypes.HANDLE
        process_first = kernel32.Process32FirstW
        process_first.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        process_first.restype = wintypes.BOOL
        process_next = kernel32.Process32NextW
        process_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        process_next.restype = wintypes.BOOL
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        query_image_name = kernel32.QueryFullProcessImageNameW
        query_image_name.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        query_image_name.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        snapshot = create_snapshot(_TH32CS_SNAPPROCESS, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())

        process_ids_by_path: dict[str, set[int]] = {}
        try:
            entry = _ProcessEntry32W()
            entry.dwSize = ctypes.sizeof(entry)
            if not process_first(snapshot, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != _ERROR_NO_MORE_FILES:
                    raise ctypes.WinError(error)
                raise OSError("Windows не вернула список активных процессов")

            while True:
                process = open_process(
                    _PROCESS_QUERY_LIMITED_INFORMATION,
                    False,
                    entry.th32ProcessID,
                )
                if process:
                    try:
                        buffer = ctypes.create_unicode_buffer(_MAX_EXECUTABLE_PATH)
                        size = wintypes.DWORD(len(buffer))
                        if query_image_name(process, 0, buffer, ctypes.byref(size)):
                            normalized_path = ProcessService._normalize_executable_path(
                                buffer.value
                            )
                            process_ids_by_path.setdefault(normalized_path, set()).add(
                                entry.th32ProcessID
                            )
                    finally:
                        close_handle(process)

                if not process_next(snapshot, ctypes.byref(entry)):
                    error = ctypes.get_last_error()
                    if error != _ERROR_NO_MORE_FILES:
                        raise ctypes.WinError(error)
                    break
        finally:
            close_handle(snapshot)
        if not process_ids_by_path:
            raise OSError("Windows не вернула пути активных процессов")
        return process_ids_by_path

    def stop(self, applications: list[ApplicationEntry]) -> ActionReport:
        report = ActionReport("Остановка")
        if not applications:
            return report

        try:
            running_processes = self._running_process_ids_by_path()
        except OSError as exc:
            for application in applications:
                report.failed.append(
                    f"{application.name}: не удалось проверить запущенные процессы: {exc}"
                )
            return report

        seen_paths: set[str] = set()
        for application in applications:
            normalized_path = self._normalize_executable_path(application.path)
            if normalized_path in seen_paths:
                report.skipped.append(application.name)
                continue
            seen_paths.add(normalized_path)
            process_ids = running_processes.get(normalized_path)
            if not process_ids:
                report.skipped.append(application.name)
                continue

            terminated = False
            failures: list[str] = []
            for process_id in sorted(process_ids):
                try:
                    completed = subprocess.run(
                        ["taskkill", "/PID", str(process_id), "/F", "/T"],
                        check=False,
                        capture_output=True,
                        text=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except OSError as exc:
                    failures.append(f"PID {process_id}: {exc}")
                    continue
                if completed.returncode == 0:
                    terminated = True
                elif completed.returncode != 128:
                    detail = (completed.stderr or completed.stdout).strip()
                    failures.append(
                        f"PID {process_id}: "
                        f"{detail or 'taskkill завершился с ошибкой'}"
                    )

            if failures:
                report.failed.append(f"{application.name}: {'; '.join(failures)}")
            elif terminated:
                report.succeeded.append(application.name)
            else:
                report.skipped.append(application.name)
        return report
