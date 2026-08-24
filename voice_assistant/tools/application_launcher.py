from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


APPLICATION_DIRS = (
    Path("/usr/share/applications"),
    Path.home() / ".local/share/applications",
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


@dataclass(frozen=True)
class DesktopApplication:
    desktop_id: str
    name: str
    path: Path


class ApplicationLauncher:
    def __init__(self) -> None:
        self.applications = self._index_applications()
        self.launcher = self._find_launcher()

        print(
            f"[applications] indexed: {len(self.applications)}"
        )
        print(
            f"[applications] launcher: "
            f"{self.launcher or 'not found'}"
        )

    # ---------------------------------------------------------
    # Index .desktop files
    # ---------------------------------------------------------

    def _index_applications(self) -> list[DesktopApplication]:
        applications: list[DesktopApplication] = []

        for directory in APPLICATION_DIRS:
            if not directory.is_dir():
                continue

            desktop_files = list(directory.glob("*.desktop"))

            print(
                f"[applications] scanning {directory}: "
                f"{len(desktop_files)} desktop files"
            )

            for path in desktop_files:
                application = self._parse_desktop_file(path)

                if application is not None:
                    applications.append(application)

        return applications

    def _parse_desktop_file(
        self,
        path: Path,
    ) -> DesktopApplication | None:

        try:
            content = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            return None

        in_desktop_entry = False

        entry_type = None
        name = None
        hidden = False
        no_display = False

        for raw_line in content.splitlines():
            line = raw_line.strip()

            if line.startswith("["):
                in_desktop_entry = line == "[Desktop Entry]"
                continue

            if not in_desktop_entry:
                continue

            if line.startswith("Type="):
                entry_type = line[5:].strip()

            elif line.startswith("Name="):
                name = line[5:].strip()

            elif line == "Hidden=true":
                hidden = True

            elif line == "NoDisplay=true":
                no_display = True

        if entry_type != "Application":
            return None

        if not name:
            return None

        if hidden or no_display:
            return None

        return DesktopApplication(
            desktop_id=path.stem,
            name=name,
            path=path,
        )
    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------

    @staticmethod
    def _normalize(value: str) -> str:
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
    ) -> DesktopApplication | None:

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

    @staticmethod
    def _find_launcher() -> str | None:
        if shutil.which("gio"):
            return "gio"

        return None

    def launch(
        self,
        query: str,
    ) -> tuple[bool, str]:

        if self.launcher is None:
            return (
                False,
                "Не найден gio.",
            )

        application = self.find(query)

        if application is None:
            return (
                False,
                f"Приложение не найдено: {query}",
            )

        try:
            command = [
                "gio",
                "launch",
                str(application.path),
            ]

            print(
                f"[applications] launching: "
                f"{' '.join(command)}"
            )

            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            print(
                f"[applications] launcher PID: "
                f"{process.pid}"
            )

            return (
                True,
                f"Открываю {application.name}",
            )

        except OSError as exc:
            return (
                False,
                f"Не удалось открыть {application.name}: {exc}",
            )