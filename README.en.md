<p align="center"><img src="assets/app-icon.png" width="96" alt="AppCircuit icon"></p>
<h1 align="center">AppCircuit</h1>
<p align="center">Launch programs and open files in your chosen order with one session.</p>
<p align="center"><a href="README.md">Русский</a> · <a href="https://github.com/Frommer-droid/AppCircuit/releases/latest">Latest release</a></p>

AppCircuit is a Windows 10/11 desktop application for sequences of program
launches, program stops, file opens, and pauses. Enabled steps run in order.
Sessions are stored locally.

## Install and get started

1. Download the installer from the [latest release](https://github.com/Frommer-droid/AppCircuit/releases/latest) and install AppCircuit.
2. Click “Новая” (New) to create a session, then add programs or files.
3. Choose an action for each step, add pauses if needed, and click “Применить сессию” (Apply session).

For an `.exe`, choose Launch or Stop. Other files open in their Windows default
application. AppCircuit skips a program already running from the same full path;
Stop targets that copy and its child processes. Stopping an elevated program may
require running AppCircuit with administrator rights.

## Sessions and standalone EXE

- Checkboxes beside session names choose which sessions go into a JSON export.
- Import adds new sessions and replaces only sessions with matching names.
- “Создать EXE” (Create EXE) uses the highlighted session, regardless of its
  export checkbox. The generated file runs a snapshot of enabled steps without
  opening AppCircuit or requiring Python. Recreate it after editing the session.

Session paths are absolute: programs and documents must stay at those paths.
User `settings.json` and the log live beside AppCircuit.exe and are excluded from
the installer.

## Run from source

Requires Windows 10/11 and Python 3.12. From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\pythonw.exe .\AppCircuit.py
```

Run tests with `.\.venv\Scripts\python.exe -m pytest` and lint with
`.\.venv\Scripts\python.exe -m ruff check .`. See [DEVELOPER.md](DEVELOPER.md)
for builds and [RELEASE_NOTES.md](RELEASE_NOTES.md) for release history.

## Limits and license

Launch steps do not support individual command-line arguments. A generated EXE
stores a session snapshot; it does not contain the target programs or files.

AppCircuit's own code is licensed under [MIT](LICENSE). Third-party terms are
listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[QT_PYSIDE6_COMPLIANCE.md](QT_PYSIDE6_COMPLIANCE.md).
