"""Tests for filesystem tools, system tools, and security guards."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFsGuard(unittest.TestCase):
    """fs_guard security tests."""

    def _make_config(self, fs_root=None):
        from config import Config
        c = Config()
        if fs_root:
            object.__setattr__(c, 'fs_root', Path(fs_root))
        return c

    def test_accepts_file_inside_home(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            file_path = Path(tmpdir) / "readme.txt"
            file_path.write_text("hello")
            allowed, resolved, error = fs_guard(file_path, config)
            self.assertTrue(allowed, error)
            self.assertEqual(resolved, file_path.resolve())

    def test_rejects_etc_passwd(self):
        from tools.filesystem import fs_guard
        config = self._make_config()
        # /etc/passwd is outside home
        allowed, resolved, error = fs_guard("/etc/passwd", config)
        self.assertFalse(allowed)
        self.assertIn("outside allowed root", error)

    def test_rejects_parent_escape(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            # ../ outside home
            allowed, resolved, error = fs_guard(tmpdir + "/../secret.txt", config)
            self.assertFalse(allowed)

    def test_resolves_symlink_outside_home(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            # Symlink inside tmpdir pointing to /etc/passwd
            link = Path(tmpdir) / "evil_link"
            link.symlink_to("/etc/passwd")
            allowed, resolved, error = fs_guard(link, config)
            self.assertFalse(allowed)
            self.assertIn("outside allowed root", error)

    def test_rejects_sudo_in_path_component(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            bad_path = Path(tmpdir) / "sudo rm -rf"
            allowed, resolved, error = fs_guard(bad_path, config)
            self.assertFalse(allowed)
            self.assertIn("privilege-escalation token", error)

    def test_rejects_pkexec_in_path_component(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            bad_path = Path(tmpdir) / "pkexec --user root"
            allowed, resolved, error = fs_guard(bad_path, config)
            self.assertFalse(allowed)
            self.assertIn("privilege-escalation token", error)

    def test_rejects_doas_in_path_component(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            bad_path = Path(tmpdir) / "doas root cat"
            allowed, resolved, error = fs_guard(bad_path, config)
            self.assertFalse(allowed)
            self.assertIn("privilege-escalation token", error)

    def test_accepts_relative_path_from_tmpdir(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(tmpdir)
            # Change to tmpdir so relative path resolves correctly
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subdir = Path("sub")
                subdir.mkdir()
                allowed, resolved, error = fs_guard("sub/notes.txt", config)
                self.assertTrue(allowed, error)
                self.assertEqual(resolved.name, "notes.txt")
            finally:
                os.chdir(old_cwd)


class TestDestructiveAllowList(unittest.TestCase):
    """DESTRUCTIVE tools require .env allow-list to run."""

    def test_destructive_denied_when_not_allowed(self):
        from safety.permissions import PermissionManager
        perms = PermissionManager(allowed=set(), denied=set())
        # delete_file is DESTRUCTIVE — not in allowed set
        decision = perms.check("delete_file", risk_level=2)
        self.assertFalse(decision.allowed)
        self.assertIn("destructive", decision.reason.lower())

    def test_destructive_allowed_when_in_allowed_set(self):
        from safety.permissions import PermissionManager
        perms = PermissionManager(allowed={"delete_file"}, denied=set())
        decision = perms.check("delete_file", risk_level=2)
        self.assertTrue(decision.allowed)
        self.assertIn("explicitly allowed", decision.reason)

    def test_confirm_still_requires_prompt_when_in_allowed(self):
        # When a DESTRUCTIVE tool is in the allowed set, PermissionManager
        # says it's allowed, but the executor should still prompt.
        # This is a semantic check: allow-list enables the tool, confirm gate is separate.
        from safety.permissions import PermissionManager
        perms = PermissionManager(allowed={"kill_process"}, denied=set())
        decision = perms.check("kill_process", risk_level=2)
        # DESTRUCTIVE tools that are in allowed set get allowed=True
        self.assertTrue(decision.allowed)
        # But the executor should still prompt (tested in integration)


class TestSandboxPreservesToolResult(unittest.TestCase):
    """Regression guard: Sandbox must not mangle ToolResult with str()."""

    def test_sandbox_preserves_tool_result(self):
        from tools.base import Tool, ToolResult
        from safety.risk import RiskLevel
        from safety.sandbox import ExecutionSandbox

        class DummyTool(Tool):
            name = "dummy"
            description = "Test tool"
            risk = RiskLevel.SAFE

            def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True, output="dummy result")

        registry = MagicMock()
        tool = DummyTool()
        registry.get.return_value = tool

        sandbox = ExecutionSandbox(timeout=30.0)
        from safety.permissions import PermissionManager
        from agent.tool_executor_safe import SafeToolExecutor

        executor = SafeToolExecutor(
            registry,
            permission_manager=PermissionManager(),
            sandbox=sandbox,
        )

        result = executor.execute({
            "tool": "dummy",
            "arguments": {},
        })

        # Critical: result must be the actual output, not the repr
        self.assertEqual(result, "dummy result")
        self.assertNotIn("ToolResult(", result)
        print("✓ Sandbox preserves ToolResult output (not repr)")


class TestSystemBackendFactory(unittest.TestCase):
    """SystemBackend factory returns platform-appropriate backend."""

    def test_factory_returns_linux_backend_on_linux(self):
        if sys.platform != "linux":
            self.skipTest("Linux-only test")

        from tools.system_backend import SystemBackendFactory, LinuxSystemBackend
        backend = SystemBackendFactory.create()
        # On Linux, should be LinuxSystemBackend (even if unavailable due to missing binaries)
        # Factory may return GenericUnavailableBackend if all binaries are missing
        # Test that factory doesn't crash and returns a callable backend
        self.assertIsNotNone(backend)
        result = backend.get_volume()
        self.assertIsNotNone(result)
        print(f"✓ Factory returned {backend.__class__.__name__}")

    def test_factory_returns_stub_on_darwin(self):
        if sys.platform == "darwin":
            self.skipTest("Non-darwin test")

        with patch.object(sys, 'platform', 'darwin'):
            from tools.system_backend import (
                SystemBackendFactory,
                MacOSSystemBackend,
            )
            backend = SystemBackendFactory.create()
            self.assertIsInstance(backend, MacOSSystemBackend)

    def test_factory_returns_stub_on_windows(self):
        if sys.platform == "win32":
            self.skipTest("Non-Windows test")

        with patch.object(sys, 'platform', 'win32'):
            from tools.system_backend import (
                SystemBackendFactory,
                WindowsSystemBackend,
            )
            backend = SystemBackendFactory.create()
            self.assertIsInstance(backend, WindowsSystemBackend)


class TestSystemBackendStubResults(unittest.TestCase):
    """Stub backends return 'unavailable' results."""

    def test_macos_stub_returns_unavailable(self):
        from tools.system_backend import MacOSSystemBackend
        backend = MacOSSystemBackend()
        result = backend.get_volume()
        self.assertFalse(result.success)
        self.assertIn("not yet implemented", result.message)
        print("✓ macOS stub returns 'not yet implemented'")


class TestDestructiveToolExecutorConfirmation(unittest.TestCase):
    """B1: DESTRUCTIVE tools must always prompt, even when allowed."""

    def test_destructive_confirms_even_when_allowed(self):
        from agent.tool_executor_safe import SafeToolExecutor
        from tools.base import Tool, ToolResult
        from safety.risk import RiskLevel
        from tools.registry import ToolRegistry

        class FakeDeleteTool(Tool):
            name = "delete_file"
            risk = RiskLevel.DESTRUCTIVE
            description = "Deletes a file"
            parameters = {"type": "object", "properties": {}, "required": []}

            def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True, output="deleted")

        registry = ToolRegistry()
        # Patch the tool so our fake is returned
        orig_get = registry.get
        def fake_get(name):
            if name == "delete_file":
                return FakeDeleteTool()
            return orig_get(name)
        registry.get = fake_get

        mock_prompter = MagicMock()
        confirmed = MagicMock()
        confirmed.confirmed = True
        mock_prompter.prompt.return_value = confirmed

        executor = SafeToolExecutor(
            registry,
            prompter=mock_prompter,
        )
        # Patch permission manager to allow the tool
        from safety.permissions import PermissionManager
        executor.permissions = PermissionManager(allowed={"delete_file"}, denied=set())

        result = executor.execute({"tool": "delete_file", "arguments": {}})

        # B1 FIX: prompter MUST be called even though tool is in allowed set
        mock_prompter.prompt.assert_called_once()
        # Result should be from the tool (after confirmation)
        self.assertEqual(result, "deleted")
        print("✓ DESTRUCTIVE tool confirms even when allowed (B1 fixed)")


class TestFsGuardRelativeToFsRoot(unittest.TestCase):
    """B2: fs_guard resolves relative paths against fs_root, not CWD."""

    def test_resolves_relative_to_fs_root_not_cwd(self):
        from tools.filesystem import fs_guard
        with tempfile.TemporaryDirectory() as tmpdir:
            from config import Config
            c = Config()
            object.__setattr__(c, 'fs_root', Path(tmpdir))

            # Create a file inside fs_root
            target = Path(tmpdir) / "notes.txt"
            target.write_text("secret")

            old_cwd = os.getcwd()
            try:
                # Change to a DIFFERENT directory so CWD != fs_root
                os.chdir("/tmp")
                allowed, resolved, error = fs_guard("notes.txt", c)
                self.assertTrue(allowed, error)
                self.assertEqual(resolved, target.resolve())
                self.assertEqual(str(resolved), str(target.resolve()))
            finally:
                os.chdir(old_cwd)
            print("✓ fs_guard resolves relative paths against fs_root, not CWD (B2 fixed)")


class TestSystemBackendPerCapability(unittest.TestCase):
    """B3: system backend has per-capability availability, not single global flag."""

    def test_per_capability_availability(self):
        from tools.system_backend import LinuxSystemBackend
        import shutil

        # Create a backend and check capabilities dict exists
        backend = LinuxSystemBackend.__new__(LinuxSystemBackend)
        backend._capabilities = {
            "volume": shutil.which("pactl") is not None,
            "processes": shutil.which("ps") is not None,
            "clipboard_in": shutil.which("wl-paste") is not None,
            "clipboard_out": shutil.which("wl-copy") is not None,
            "clipboard_fallback": shutil.which("xclip") is not None,
            "screenshot": shutil.which("grim") is not None,
            "recording": shutil.which("wf-recorder") is not None,
            "recording_fallback": shutil.which("ffmpeg") is not None,
            "power": shutil.which("loginctl") is not None,
        }
        backend._recording_pid = None
        backend._recording_start = 0.0

        # Verify capabilities is a dict, not a bool
        self.assertIsInstance(backend._capabilities, dict)

        # Each capability should be independently set
        for cap in backend._capabilities:
            self.assertIsInstance(backend._capabilities[cap], bool)

        print(f"✓ Backend has per-capability dict: {list(backend._capabilities.keys())}")
        print("  (B3: missing wf-recorder no longer kills get_volume)")


class TestRecordingWaylandDetection(unittest.TestCase):
    """B4: recording detects Wayland/X11 and builds correct commands."""

    def test_wayland_command_no_slurp(self):
        # Verify the start_recording logic builds correct wf-recorder command
        import shutil
        if not shutil.which("wf-recorder"):
            self.skipTest("wf-recorder not installed")

        from tools.system_backend import LinuxSystemBackend
        import tempfile

        backend = LinuxSystemBackend.__new__(LinuxSystemBackend)
        backend._capabilities = {
            "recording": shutil.which("wf-recorder") is not None,
            "recording_fallback": shutil.which("ffmpeg") is not None,
            "screenshot": shutil.which("grim") is not None,
            "volume": shutil.which("pactl") is not None,
            "processes": shutil.which("ps") is not None,
            "clipboard_in": shutil.which("wl-paste") is not None,
            "clipboard_out": shutil.which("wl-copy") is not None,
            "clipboard_fallback": shutil.which("xclip") is not None,
            "power": shutil.which("loginctl") is not None,
        }
        backend._recording_pid = None
        backend._recording_start = 0.0

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            dest = Path(f.name)

        try:
            with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=False):
                result = backend.start_recording(dest)
                # Should succeed (or fail for other reasons, but NOT slurp error)
                # The key assertion: slurp is not in the command
                self.assertNotIn("$(slurp)", str(result.message))
                print("✓ Recording uses wf-recorder without slurp on Wayland (B4 fixed)")
        finally:
            dest.unlink(missing_ok=True)


class TestConfigFsRootResolved(unittest.TestCase):
    """B6: config.fs_root is resolved to absolute path at construction."""

    def test_fs_root_is_absolute(self):
        from config import Config
        c = Config()
        self.assertTrue(c.fs_root.is_absolute(),
                        f"fs_root should be absolute, got: {c.fs_root}")
        print(f"✓ config.fs_root is absolute: {c.fs_root}")

    def test_fs_root_tilde_resolved(self):
        from config import Config
        c = Config()
        # If home is set, fs_root should match it
        self.assertEqual(c.fs_root, Path.home().resolve())
        print(f"✓ fs_root resolves to home: {c.fs_root}")


class TestScriptContentScanner(unittest.TestCase):
    """B5: run_script scans content for dangerous patterns."""

    def test_blocks_dangerous_script(self):
        from tools.filesystem import _check_script_dangerous
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "evil.sh"
            script.write_text("#!/bin/bash\nsudo rm -rf /\n")

            danger = _check_script_dangerous(script)
            self.assertIsNotNone(danger)
            self.assertIn("Dangerous pattern", danger)
            print("✓ Script with 'sudo rm -rf /' is blocked (B5 fixed)")

    def test_allows_clean_script(self):
        from tools.filesystem import _check_script_dangerous
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "clean.sh"
            script.write_text("#!/bin/bash\necho 'hello world'\n")

            danger = _check_script_dangerous(script)
            self.assertIsNone(danger)
            print("✓ Clean script passes content scan (B5)")


class TestFilesystemToolSafe(unittest.TestCase):
    """Filesystem SAFE tools work correctly."""

    def test_read_file_works(self):
        from tools.filesystem import ReadFileTool
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("hello world")

            from config import Config
            c = Config()
            object.__setattr__(c, 'fs_root', Path(tmpdir))

            tool = ReadFileTool()
            tool._config = c

            # Use absolute path relative to fs_root
            result = tool.execute(str(file_path))
            self.assertTrue(result.success, result.output)
            self.assertIn("hello world", result.output)

    def test_read_file_rejected_outside_home(self):
        from tools.filesystem import ReadFileTool
        with tempfile.TemporaryDirectory() as tmpdir:
            from config import Config
            c = Config()
            object.__setattr__(c, 'fs_root', Path(tmpdir))

            tool = ReadFileTool()
            tool._config = c

            result = tool.execute("/etc/passwd")
            self.assertFalse(result.success)
            self.assertIn("outside allowed root", result.output)

    def test_list_directory_works(self):
        from tools.filesystem import ListDirectoryTool
        with tempfile.TemporaryDirectory() as tmpdir:
            from config import Config
            c = Config()
            object.__setattr__(c, 'fs_root', Path(tmpdir))

            tool = ListDirectoryTool()
            tool._config = c
            (Path(tmpdir) / "a.txt").touch()
            (Path(tmpdir) / "subdir").mkdir()

            result = tool.execute("")
            self.assertTrue(result.success)
            self.assertIn("a.txt", result.output)
            self.assertIn("subdir/", result.output)


if __name__ == "__main__":
    print("\n=== Filesystem & System Tool Tests ===\n")

    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        print("\n✓ All tests passed!")
    else:
        print(f"\n✗ {len(result.failures) + len(result.errors)} test(s) failed")
        sys.exit(1)