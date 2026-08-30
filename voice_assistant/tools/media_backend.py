from __future__ import annotations

import abc
import shutil
import subprocess


class MediaBackendResult:
    """Result from a media backend operation."""

    def __init__(self, success: bool, message: str):
        self.success = success
        self.message = message


class MediaBackend(abc.ABC):
    """Platform-agnostic interface for media playback control."""

    @abc.abstractmethod
    def play(self) -> MediaBackendResult:
        """Resume playback."""
        raise NotImplementedError

    @abc.abstractmethod
    def pause(self) -> MediaBackendResult:
        """Pause playback."""
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self) -> MediaBackendResult:
        """Stop playback."""
        raise NotImplementedError

    @abc.abstractmethod
    def next(self) -> MediaBackendResult:
        """Skip to next track."""
        raise NotImplementedError

    @abc.abstractmethod
    def previous(self) -> MediaBackendResult:
        """Go to previous track."""
        raise NotImplementedError

    @abc.abstractmethod
    def status(self) -> MediaBackendResult:
        """Get current playback status (title + state)."""
        raise NotImplementedError


class LinuxMPRISBackend(MediaBackend):
    """Media backend using playerctl (MPRIS/D-Bus)."""

    def __init__(self):
        self._available = shutil.which("playerctl") is not None

    def _run_playerctl(self, *args: str) -> tuple[bool, str]:
        """Run playerctl command and return (success, output)."""
        if not self._available:
            return (False, "Media control is not available on this system")

        try:
            result = subprocess.run(
                ["playerctl", *args],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                error = result.stderr.strip() or f"playerctl exited {result.returncode}"
                # Common errors
                if "No players found" in error or "Could not find player" in error:
                    return (False, "No media player is running")
                return (False, f"Command failed: {error}")

            return (True, result.stdout.strip())

        except subprocess.TimeoutExpired:
            return (False, "Command timed out")
        except Exception as exc:
            return (False, f"Unexpected error: {exc}")

    def play(self) -> MediaBackendResult:
        success, message = self._run_playerctl("play")
        if success:
            return MediaBackendResult(True, "Playback resumed")
        return MediaBackendResult(False, message)

    def pause(self) -> MediaBackendResult:
        success, message = self._run_playerctl("pause")
        if success:
            return MediaBackendResult(True, "Playback paused")
        return MediaBackendResult(False, message)

    def stop(self) -> MediaBackendResult:
        success, message = self._run_playerctl("stop")
        if success:
            return MediaBackendResult(True, "Playback stopped")
        return MediaBackendResult(False, message)

    def next(self) -> MediaBackendResult:
        success, message = self._run_playerctl("next")
        if success:
            return MediaBackendResult(True, "Skipped to next track")
        return MediaBackendResult(False, message)

    def previous(self) -> MediaBackendResult:
        success, message = self._run_playerctl("previous")
        if success:
            return MediaBackendResult(True, "Went to previous track")
        return MediaBackendResult(False, message)

    def status(self) -> MediaBackendResult:
        # Get playback state
        success_state, state = self._run_playerctl("status")
        if not success_state:
            return MediaBackendResult(False, state)

        # Get track metadata (artist - title)
        success_meta, metadata = self._run_playerctl(
            "metadata", "--format", "{{artist}} - {{title}}"
        )

        if success_meta and metadata.strip():
            track = metadata.strip()
            return MediaBackendResult(True, f"{track} ({state})")
        else:
            # No track info, just return state
            return MediaBackendResult(True, f"{state} (no track info)")


class UnavailableMediaBackend(MediaBackend):
    """Stub backend when media control is not available."""

    def play(self) -> MediaBackendResult:
        return MediaBackendResult(False, "Media control is not available on this system")

    def pause(self) -> MediaBackendResult:
        return MediaBackendResult(False, "Media control is not available on this system")

    def stop(self) -> MediaBackendResult:
        return MediaBackendResult(False, "Media control is not available on this system")

    def next(self) -> MediaBackendResult:
        return MediaBackendResult(False, "Media control is not available on this system")

    def previous(self) -> MediaBackendResult:
        return MediaBackendResult(False, "Media control is not available on this system")

    def status(self) -> MediaBackendResult:
        return MediaBackendResult(False, "Media control is not available on this system")


class MediaBackendFactory:
    """Factory for creating platform-specific media backends."""

    @staticmethod
    def create() -> MediaBackend:
        """
        Create a media backend for the current platform.

        Returns:
            MediaBackend instance (LinuxMPRISBackend or UnavailableMediaBackend)
        """
        if shutil.which("playerctl"):
            return LinuxMPRISBackend()

        return UnavailableMediaBackend()
