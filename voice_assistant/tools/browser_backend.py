from __future__ import annotations

from abc import ABC, abstractmethod
import shutil
import subprocess


class BrowserBackend(ABC):
    """Abstract interface for opening URLs in browser."""

    @abstractmethod
    def open_url(self, url: str) -> tuple[bool, str]:
        """
        Open URL in default browser.

        Args:
            url: The URL to open

        Returns:
            Tuple of (success: bool, message: str)
        """
        raise NotImplementedError


class XdgBrowserOpener(BrowserBackend):
    """Linux xdg-open browser launcher."""

    def open_url(self, url: str) -> tuple[bool, str]:
        """Open URL using xdg-open (FreeDesktop standard)."""
        try:
            subprocess.Popen(
                [
                    "xdg-open",
                    url,
                ]
            )

            return (True, f"Открываю браузер: {url}")

        except Exception as exc:
            return (False, f"Ошибка открытия браузера: {exc}")


class BrowserFactory:
    """Factory for creating platform-specific browser openers."""

    @staticmethod
    def create() -> BrowserBackend:
        """
        Create a browser opener for the current platform.

        Returns:
            BrowserBackend instance for the detected platform

        Raises:
            RuntimeError: If no browser backend is available
        """
        if shutil.which("xdg-open"):
            return XdgBrowserOpener()

        # Future platform support:
        # elif sys.platform == "darwin":
        #     return MacOSBrowserOpener()  # uses 'open'
        # elif sys.platform == "win32":
        #     return WindowsBrowserOpener()  # uses 'start'

        raise RuntimeError(
            "No browser backend available. "
            "Install xdg-utils (xdg-open) to enable browser opening."
        )
