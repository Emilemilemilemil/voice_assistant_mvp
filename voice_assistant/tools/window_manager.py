from __future__ import annotations

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass


# =========================================================
# Window model
# =========================================================

@dataclass(frozen=True)
class Window:
    address: str
    window_class: str
    title: str
    pid: int


# =========================================================
# Backend interface
# =========================================================

class WindowBackend(ABC):

    @abstractmethod
    def close_window(self, target: str) -> tuple[bool, str]:
        raise NotImplementedError


# =========================================================
# Hyprland backend
# =========================================================

class HyprlandWindowBackend(WindowBackend):

    def __init__(self) -> None:
        if shutil.which("hyprctl") is None:
            raise RuntimeError(
                "hyprctl не найден. "
                "Hyprland backend недоступен."
            )

    # -----------------------------------------------------
    # Get windows
    # -----------------------------------------------------

    def _get_windows(self) -> list[Window]:

        result = subprocess.run(
            [
                "hyprctl",
                "clients",
                "-j",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error = (
                result.stderr.strip()
                or result.stdout.strip()
                or "неизвестная ошибка"
            )

            raise RuntimeError(
                f"Не удалось получить список окон: {error}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Hyprland вернул некорректный JSON: {exc}"
            ) from exc

        windows: list[Window] = []

        for item in data:
            address = item.get("address")
            window_class = item.get("class")
            title = item.get("title")
            pid = item.get("pid", 0)

            if not address:
                continue

            windows.append(
                Window(
                    address=address,
                    window_class=window_class or "",
                    title=title or "",
                    pid=pid,
                )
            )

        return windows

    # -----------------------------------------------------
    # Normalization
    # -----------------------------------------------------

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            value.lower().strip().split()
        )

    # -----------------------------------------------------
    # Find windows
    # -----------------------------------------------------

    def _find_windows(
        self,
        target: str,
    ) -> list[Window]:

        query = self._normalize(target)

        if not query:
            return []

        windows = self._get_windows()

        # -------------------------------------------------
        # 1. Exact class
        # -------------------------------------------------

        exact_class = [
            window
            for window in windows
            if self._normalize(window.window_class) == query
        ]

        if exact_class:
            return exact_class

        # -------------------------------------------------
        # 2. Exact title
        # -------------------------------------------------

        exact_title = [
            window
            for window in windows
            if self._normalize(window.title) == query
        ]

        if exact_title:
            return exact_title

        # -------------------------------------------------
        # 3. Class contains query
        # -------------------------------------------------

        class_matches = [
            window
            for window in windows
            if query in self._normalize(window.window_class)
        ]

        if class_matches:
            return class_matches

        # -------------------------------------------------
        # 4. Title contains query
        # -------------------------------------------------

        title_matches = [
            window
            for window in windows
            if query in self._normalize(window.title)
        ]

        if title_matches:
            return title_matches

        return []

    # -----------------------------------------------------
    # Close window
    # -----------------------------------------------------

    def close_window(
        self,
        target: str,
    ) -> tuple[bool, str]:

        matches = self._find_windows(target)

        # -------------------------------------------------
        # Window not found
        # -------------------------------------------------

        if not matches:
            return (
                False,
                f"Окно не найдено: {target}",
            )

        # -------------------------------------------------
        # Multiple windows
        # -------------------------------------------------

        if len(matches) > 1:

            names = ", ".join(
                window.title
                for window in matches
            )

            return (
                False,
                f"Найдено несколько окон: {names}",
            )

        window = matches[0]

        # -------------------------------------------------
        # Hyprland 0.55+ Lua dispatcher
        # -------------------------------------------------

        selector = f"address:{window.address}"

        lua_dispatch = (
            f'hl.dsp.window.close({{ window = "{selector}" }})'
        )

        result = subprocess.run(
            [
                "hyprctl",
                "dispatch",
                lua_dispatch,
            ],
            capture_output=True,
            text=True,
        )

        # -------------------------------------------------
        # Command failed
        # -------------------------------------------------

        if result.returncode != 0:

            error = (
                result.stderr.strip()
                or result.stdout.strip()
                or "неизвестная ошибка"
            )

            return (
                False,
                f"Не удалось закрыть окно: {error}",
            )

        # -------------------------------------------------
        # Success
        # -------------------------------------------------

        return (
            True,
            f"Закрываю {window.title}",
        )


# =========================================================
# Window manager
# =========================================================

class WindowManager:

    def __init__(self) -> None:
        self.backend = self._create_backend()

    @staticmethod
    def _create_backend() -> WindowBackend:
        try:
            if shutil.which("hyprctl"):
                return HyprlandWindowBackend()
        except RuntimeError:
            pass

        # Future: GNOME (gdbus), KDE (qdbus), macOS (osascript), Windows (WMI)
        # All backends should implement WindowBackend interface
        raise RuntimeError(
            "Поддерживаемый оконный менеджер не найден. "
            "Установите Hyprland или настройте альтернативный бэкенд."
        )

    # -----------------------------------------------------
    # Public API
    # -----------------------------------------------------

    def close_window(
        self,
        target: str,
    ) -> tuple[bool, str]:

        return self.backend.close_window(target)