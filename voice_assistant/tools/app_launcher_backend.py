from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class Application:
    """Platform-agnostic application representation."""
    id: str           # Linux: desktop_id, macOS: bundle_id, Windows: exe_name
    name: str         # Display name
    path: Path        # Linux: .desktop path, macOS: .app path, Windows: .exe path


class AppLauncherBackend(ABC):
    """Abstract interface for app launching."""

    @abstractmethod
    def index_applications(self) -> list[Application]:
        """
        Scan system for installed applications.

        Returns:
            List of Application instances found on the system
        """
        raise NotImplementedError

    @abstractmethod
    def launch(self, app: Application) -> tuple[bool, str]:
        """
        Launch an application.

        Args:
            app: The Application to launch

        Returns:
            Tuple of (success: bool, message: str)
        """
        raise NotImplementedError


class LinuxDesktopLauncher(AppLauncherBackend):
    """FreeDesktop .desktop file based launcher (Linux)."""

    APPLICATION_DIRS = (
        Path("/usr/share/applications"),
        Path.home() / ".local/share/applications",
    )

    def index_applications(self) -> list[Application]:
        """Scan .desktop files from FreeDesktop directories."""
        applications: list[Application] = []

        for directory in self.APPLICATION_DIRS:
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
    ) -> Application | None:
        """Parse a .desktop file and extract application info."""

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

        return Application(
            id=path.stem,
            name=name,
            path=path,
        )

    # Security: Whitelist allowed directories - don't launch arbitrary .desktop files
    ALLOWED_DIRS = (
        Path("/usr/share/applications"),
        Path.home() / ".local/share/applications",
    )

    def launch(self, app: Application) -> tuple[bool, str]:
        """Launch application using gio launch."""
        # Security: Verify the desktop file is in an allowed directory
        allowed = False
        for allowed_dir in self.ALLOWED_DIRS:
            try:
                app.path.resolve().relative_to(allowed_dir.resolve())
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            return (False, f"Security: {app.name} is not in allowed application directory")

        # Security: Check that the .desktop file exists and is readable
        if not app.path.exists():
            return (False, f"Desktop file not found: {app.path}")
        if not app.path.is_file():
            return (False, f"Not a file: {app.path}")

        try:
            command = [
                "gio",
                "launch",
                str(app.path),
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
                f"Открываю {app.name}",
            )

        except OSError as exc:
            return (
                False,
                f"Не удалось открыть {app.name}: {exc}",
            )


class AppLauncherFactory:
    """Factory for creating platform-specific app launchers."""

    @staticmethod
    def create() -> AppLauncherBackend:
        """
        Create an app launcher for the current platform.

        Returns:
            AppLauncherBackend instance for the detected platform

        Raises:
            RuntimeError: If no app launcher backend is available
        """
        if shutil.which("gio"):
            return LinuxDesktopLauncher()

        # Future platform support:
        # elif sys.platform == "darwin":
        #     return MacOSLauncher()  # uses 'open -a', scans /Applications
        # elif sys.platform == "win32":
        #     return WindowsLauncher()  # uses Start Menu indexing

        raise RuntimeError(
            "No app launcher backend available. "
            "Install gio (glib2) to enable app launching."
        )
