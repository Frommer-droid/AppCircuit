# Доступ к исходному коду сторонних компонентов

AppCircuit использует немодифицированные динамически подключаемые библиотеки
Qt/PySide6. Пользователь может заменить совместимые DLL и компоненты Qt внутри
папки `_internal` готовой `onedir`-сборки.

Соответствующий исходный код Qt for Python и Qt доступен в официальных
репозиториях:

- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://code.qt.io/cgit/qt/
- https://download.qt.io/official_releases/QtForPython/

Точная версия поставленных компонентов записана в `RUNTIME_MANIFEST.json`.
Версии исходного кода Qt/PySide6 соответствуют версиям в `RUNTIME_MANIFEST.json`.
Исходный код AppCircuit доступен в репозитории:
https://github.com/Frommer-droid/AppCircuit
