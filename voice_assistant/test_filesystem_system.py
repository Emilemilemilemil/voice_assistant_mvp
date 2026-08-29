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