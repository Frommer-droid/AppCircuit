from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

RUSSIAN_LOCALE = QLocale(QLocale.Language.Russian, QLocale.Country.Russia)


def set_russian_locale() -> None:
    QLocale.setDefault(RUSSIAN_LOCALE)


def install_russian_translations(app: QApplication) -> list[QTranslator]:
    translator = QTranslator(app)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(RUSSIAN_LOCALE, "qtbase", "_", translations_path):
        app.installTranslator(translator)
        return [translator]
    return []
