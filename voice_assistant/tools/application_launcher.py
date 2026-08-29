from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from tools.app_launcher_backend import (
    Application,
    AppLauncherBackend,
    AppLauncherFactory,
)


ALIASES = {
    # Firefox
    "файерфокс": "firefox",
    "фаерфокс": "firefox",
    "файрфокс": "firefox",
    "фаирфокс": "firefox",

    # Chrome
    "хром": "google chrome",
    "гугл хром": "google chrome",
    "chrome": "google chrome",


    # Discord
    "дискорд": "discord",

    # Telegram
    "телеграм": "telegram",


    # VS Code
    "вс код": "visual studio code",
    "вс коде": "visual studio code",
    "vs code": "visual studio code",

    # Terminal / Kitty
    "терминал": "kitty",

    # Yandex Music
    "яндекс музыка": "yandex music",
    "яндекс музыку": "yandex music",
}


class ApplicationLauncher:
    def __init__(self) -> None:
        self.backend = AppLauncherFactory.create()
        self.applications = self.backend.index_applications()

        print(
            f"[applications] indexed: {len(self.applications)}"
        )

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------

    @staticmethod
    def _normalize(value: str) -> str:
        # Normalize Unicode (NFKC form handles composed/decomposed forms)
        value = unicodedata.normalize("NFKC", value)
        value = value.lower().strip()

        value = value.replace("ё", "е")

        value = re.sub(
            r"[^a-zа-я0-9\s]+",
            " ",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    def _canonicalize(self, value: str) -> str:
        value = self._normalize(value)

        return ALIASES.get(value, value)

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------

    def find(
        self,
        query: str,
    ) -> Application | None:

        query = self._canonicalize(query)

        if not query:
            return None

        # Exact name
        for app in self.applications:
            name = self._normalize(app.name)

            if name == query:
                return app

        # Query inside name
        for app in self.applications:
            name = self._normalize(app.name)

            if query in name:
                return app

        # Name inside query
        for app in self.applications:
            name = self._normalize(app.name)

            if name in query:
                return app

        # Fuzzy search
        best_app = None
        best_score = 0.0

        for app in self.applications:
            name = self._normalize(app.name)

            score = SequenceMatcher(
                None,
                query,
                name,
            ).ratio()

            if score > best_score:
                best_score = score
                best_app = app

        if best_score >= 0.55:
            return best_app

        return None

    # ---------------------------------------------------------
    # Launch
    # ---------------------------------------------------------

    def launch(
        self,
        query: str,
    ) -> tuple[bool, str]:

        application = self.find(query)

        if application is None:
            return (
                False,
                f"Приложение не найдено: {query}",
            )

        return self.backend.launch(application)