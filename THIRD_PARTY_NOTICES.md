# Уведомления о сторонних компонентах

Сборка AppCircuit включает стороннее программное обеспечение:

- Python — Python Software Foundation License;
- PySide6 и Shiboken6 — LGPL-3.0-only, GPL-2.0-only, GPL-3.0-only либо
  коммерческая лицензия Qt в зависимости от выбранного правообладателем режима;
- Qt 6 runtime — лицензии соответствующих модулей Qt;
- PyInstaller bootloader — GPL-2.0-or-later с исключением для распространения
  собранных приложений.

Фактические версии фиксируются в `RUNTIME_MANIFEST.json`, создаваемом после
каждой сборки. Тексты GNU LGPL v3 и GPL v3 находятся в `LGPL-3.0.txt` и
`GPL-3.0.txt`. Полные сведения и исходный код сторонних компонентов доступны на
официальных сайтах:

- https://www.python.org/downloads/source/
- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://code.qt.io/cgit/qt/
- https://github.com/pyinstaller/pyinstaller
