from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

from safety.risk import RiskLevel
from tools.base import Tool, ToolResult
from config import Config


# =========================================================
# Security guard
# =========================================================

def fs_guard(path: str | Path, config: Config) -> tuple[bool, Path, str]:
    """Validate a filesystem path against security policy.

    Rules:
      - Path must be inside config.fs_root (default: user's home).
      - Symlinks are resolved; final location is checked.
      - Absolute paths outside home are rejected.
      - Relative paths that ascend out of home are rejected.
      - Token 'sudo', 'pkexec', 'doas', 'su' in any component is rejected.

    Returns:
      (allowed, resolved_path, error_message)
    """
    if isinstance(path, str):
        path = Path(path)

    # Reject any path component containing sudo/pkexec/doas/su token
    # (defends against run_script arguments trying to escalate)
    for part in path.parts:
        if re.search(r'\b(sudo|pkexec|doas|su)\b', part, flags=re.IGNORECASE):
            return (
                False,
                path,
                f"Security: path component contains privilege-escalation token: {part}",
            )

    try:
        # Resolve symlinks, but check that the resolved path is still
        # under fs_root. This prevents symlink attacks (e.g., a symlink
        # in home pointing to /etc/passwd).
        resolved = path.resolve()
    except Exception as exc:
        return (
            False,
            path,
            f"Security: cannot resolve path: {exc}",
        )

    try:
        # Is the resolved path inside fs_root?
        resolved.relative_to(config.fs_root.resolve())
    except ValueError:
        return (
            False,
            resolved,
            f"Security: path {resolved} is outside allowed root {config.fs_root}",
        )

    return (True, resolved, "")


def validate_script_content(script_path: Path, config: Config) -> tuple[bool, str]:
    """Check that a script is safe to run.

    Currently only ensures the path passes fs_guard and the file exists.
    Future: could check shebang, forbid certain commands.
    """
    allowed, resolved, error = fs_guard(script_path, config)
    if not allowed:
        return (False, error)
    if not resolved.exists():
        return (False, f"Script file does not exist: {resolved}")
    if not resolved.is_file():
        return (False, f"Not a regular file: {resolved}")
    return (True, "")


# =========================================================
# Filesystem tools (SAFE)
# =========================================================

class ReadFileTool(Tool):
    name = "read_file"
    risk = RiskLevel.SAFE
    description = """
    Читает содержимое текстового файла.

    Аргументы:
    path: путь к файлу.

    Примеры:
    - README.md
    - notes.txt
    - project/proposal.md
    """
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к файлу (относительно домашней директории).",
            }
        },
        "required": ["path"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, path: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed, resolved, error = fs_guard(path, self._config)
        if not allowed:
            return ToolResult(success=False, output=error)

        try:
            # Respect read limits
            stat = resolved.stat()
            if stat.st_size > self._config.fs_max_read_bytes:
                return ToolResult(
                    success=False,
                    output=(
                        f"Файл слишком велик ({stat.st_size} байт). "
                        f"Ограничение: {self._config.fs_max_read_bytes} байт."
                    ),
                )

            text = resolved.read_text(encoding="utf-8", errors="replace")

            # Optionally truncate by line count
            lines = text.splitlines()
            if len(lines) > self._config.fs_max_read_lines:
                text = "\n".join(lines[: self._config.fs_max_read_lines])
                text += f"\n[... файл обрезан: {len(lines)} строк > {self._config.fs_max_read_lines}]"

            return ToolResult(success=True, output=text.strip())
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось прочитать файл: {exc}")


class ListDirectoryTool(Tool):
    name = "list_directory"
    risk = RiskLevel.SAFE
    description = """
    Показывает содержимое директории.

    Аргументы:
    path: путь к директории (по умолчанию домашняя директория).

    Примеры:
    - / (показать домашнюю директорию)
    - Documents
    - project/src
    """
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к директории (по умолчанию домашняя).",
            }
        },
        "required": [],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, path: str = "") -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        if not path:
            path = str(self._config.fs_root)

        allowed, resolved, error = fs_guard(path, self._config)
        if not allowed:
            return ToolResult(success=False, output=error)

        if not resolved.exists():
            return ToolResult(success=False, output=f"Директория не существует: {resolved}")
        if not resolved.is_dir():
            return ToolResult(success=False, output=f"Не директория: {resolved}")

        try:
            entries = []
            for entry in resolved.iterdir():
                if entry.is_dir():
                    entries.append(f"{entry.name}/")
                else:
                    entries.append(entry.name)
            entries.sort(key=str.lower)
            output = "\n".join(entries) if entries else "(пусто)"
            return ToolResult(success=True, output=output)
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось перечислить директорию: {exc}")


class SearchFilesTool(Tool):
    name = "search_files"
    risk = RiskLevel.SAFE
    description = """
    Ищет файлы по имени или содержимому внутри домашней директории.

    Аргументы:
    query: текст для поиска в именах файлов или содержимом.
    in_content: искать внутри текстовых файлов (по умолчанию false).
    limit: максимальное количество результатов (по умолчанию 20).

    Примеры:
    - README (поиск по имени)
    - TODO (поиск по содержимому)
    """
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Текст для поиска.",
            },
            "in_content": {
                "type": "boolean",
                "description": "Искать в содержимом текстовых файлов (иначе только по имени).",
                "default": False,
            },
            "limit": {
                "type": "integer",
                "description": "Максимальное количество результатов.",
                "default": 20,
            },
        },
        "required": ["query"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, query: str, in_content: bool = False, limit: int = 20) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        if limit <= 0:
            return ToolResult(success=False, output="Лимит результатов должен быть положительным.")

        try:
            from pathlib import Path
            import re
            query_re = re.compile(re.escape(query), re.IGNORECASE)
            results = []
            for entry in Path(self._config.fs_root).rglob("*"):
                if not entry.is_file():
                    continue
                # Ensure entry is still under fs_root (paranoid)
                try:
                    entry.relative_to(self._config.fs_root)
                except ValueError:
                    continue

                if in_content:
                    try:
                        text = entry.read_text(encoding="utf-8", errors="ignore")
                        if query_re.search(text):
                            results.append(str(entry.relative_to(self._config.fs_root)))
                    except Exception:
                        pass  # binary file or permission error
                else:
                    if query_re.search(entry.name):
                        results.append(str(entry.relative_to(self._config.fs_root)))

                if len(results) >= limit:
                    break

            if not results:
                return ToolResult(success=True, output="Ничего не найдено.")

            output = "\n".join(results[:limit])
            if len(results) > limit:
                output += f"\n[... найдено {len(results)} файлов, показано {limit}]"
            return ToolResult(success=True, output=output)
        except Exception as exc:
            return ToolResult(success=False, output=f"Ошибка поиска: {exc}")


# =========================================================
# Filesystem tools (CONFIRM)
# =========================================================

class WriteFileTool(Tool):
    name = "write_file"
    risk = RiskLevel.CONFIRM
    description = """
    Создаёт или перезаписывает текстовый файл.

    Аргументы:
    path: путь к файлу.
    content: содержимое файла.

    Примеры:
    - note.txt с текстом "Заметка"
    - todo.md с текстом "## Задачи"
    """
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к файлу (относительно домашней директории).",
            },
            "content": {
                "type": "string",
                "description": "Содержимое файла.",
            },
        },
        "required": ["path", "content"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, path: str, content: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed, resolved, error = fs_guard(path, self._config)
        if not allowed:
            return ToolResult(success=False, output=error)

        try:
            resolved.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Файл создан: {resolved.relative_to(self._config.fs_root)}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось записать файл: {exc}")


class CreateDirectoryTool(Tool):
    name = "create_directory"
    risk = RiskLevel.CONFIRM
    description = """
    Создаёт новую директорию.

    Аргументы:
    path: путь к новой директории.

    Примеры:
    - new_folder
    - projects/python
    """
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к новой директории (относительно домашней).",
            },
        },
        "required": ["path"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, path: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed, resolved, error = fs_guard(path, self._config)
        if not allowed:
            return ToolResult(success=False, output=error)

        try:
            resolved.mkdir(parents=True, exist_ok=True)
            return ToolResult(
                success=True,
                output=f"Директория создана: {resolved.relative_to(self._config.fs_root)}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось создать директорию: {exc}")


class CopyFileTool(Tool):
    name = "copy_file"
    risk = RiskLevel.CONFIRM
    description = """
    Копирует файл.

    Аргументы:
    source: исходный файл.
    destination: путь назначения.

    Примеры:
    - source.txt → backup/source.txt
    """
    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Путь к исходному файлу.",
            },
            "destination": {
                "type": "string",
                "description": "Путь к новому файлу.",
            },
        },
        "required": ["source", "destination"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, source: str, destination: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed_src, src_resolved, error_src = fs_guard(source, self._config)
        if not allowed_src:
            return ToolResult(success=False, output=error_src)
        allowed_dst, dst_resolved, error_dst = fs_guard(destination, self._config)
        if not allowed_dst:
            return ToolResult(success=False, output=error_dst)

        if not src_resolved.exists():
            return ToolResult(success=False, output=f"Исходный файл не существует: {src_resolved}")
        if not src_resolved.is_file():
            return ToolResult(success=False, output=f"Не файл: {src_resolved}")

        try:
            shutil.copy2(src_resolved, dst_resolved)
            return ToolResult(
                success=True,
                output=f"Скопировано: {src_resolved.relative_to(self._config.fs_root)} → {dst_resolved.relative_to(self._config.fs_root)}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось скопировать файл: {exc}")


class MoveFileTool(Tool):
    name = "move_file"
    risk = RiskLevel.CONFIRM
    description = """
    Перемещает или переименовывает файл.

    Аргументы:
    source: исходный файл.
    destination: новый путь.

    Примеры:
    - old.txt → new.txt
    - file.txt → archive/file.txt
    """
    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Путь к исходному файлу.",
            },
            "destination": {
                "type": "string",
                "description": "Новый путь.",
            },
        },
        "required": ["source", "destination"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, source: str, destination: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed_src, src_resolved, error_src = fs_guard(source, self._config)
        if not allowed_src:
            return ToolResult(success=False, output=error_src)
        allowed_dst, dst_resolved, error_dst = fs_guard(destination, self._config)
        if not allowed_dst:
            return ToolResult(success=False, output=error_dst)

        if not src_resolved.exists():
            return ToolResult(success=False, output=f"Исходный файл не существует: {src_resolved}")
        if not src_resolved.is_file():
            return ToolResult(success=False, output=f"Не файл: {src_resolved}")

        try:
            src_resolved.rename(dst_resolved)
            return ToolResult(
                success=True,
                output=f"Перемещено: {src_resolved.relative_to(self._config.fs_root)} → {dst_resolved.relative_to(self._config.fs_root)}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось переместить файл: {exc}")


# =========================================================
# Filesystem tools (DESTRUCTIVE)
# =========================================================

class DeleteFileTool(Tool):
    name = "delete_file"
    risk = RiskLevel.DESTRUCTIVE
    description = """
    Удаляет файл.

    Аргументы:
    path: путь к файлу.

    Примеры:
    - temp.txt
    - trash/old.pdf
    """
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к файлу для удаления.",
            },
        },
        "required": ["path"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, path: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed, resolved, error = fs_guard(path, self._config)
        if not allowed:
            return ToolResult(success=False, output=error)

        if not resolved.exists():
            return ToolResult(success=False, output=f"Файл не существует: {resolved}")
        if not resolved.is_file():
            return ToolResult(success=False, output=f"Не файл: {resolved}")

        try:
            resolved.unlink()
            return ToolResult(
                success=True,
                output=f"Удалён файл: {resolved.relative_to(self._config.fs_root)}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось удалить файл: {exc}")


class DeleteDirectoryTool(Tool):
    name = "delete_directory"
    risk = RiskLevel.CONFIRM
    description = """
    Удаляет директорию (только если пуста).

    Аргументы:
    path: путь к директории.

    Примеры:
    - empty_folder
    - temp/trash
    """
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к директории для удаления.",
            },
        },
        "required": ["path"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, path: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed, resolved, error = fs_guard(path, self._config)
        if not allowed:
            return ToolResult(success=False, output=error)

        if not resolved.exists():
            return ToolResult(success=False, output=f"Директория не существует: {resolved}")
        if not resolved.is_dir():
            return ToolResult(success=False, output=f"Не директория: {resolved}")

        try:
            # Only delete empty directories
            if any(resolved.iterdir()):
                return ToolResult(
                    success=False,
                    output=f"Директория не пуста: {resolved.relative_to(self._config.fs_root)}",
                )
            resolved.rmdir()
            return ToolResult(
                success=True,
                output=f"Удалена пустая директория: {resolved.relative_to(self._config.fs_root)}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось удалить директорию: {exc}")


class RunScriptTool(Tool):
    name = "run_script"
    risk = RiskLevel.DESTRUCTIVE
    description = """
    Запускает существующий скрипт внутри домашней директории.

    Аргументы:
    path: путь к скрипту.

    Примеры:
    - scripts/backup.sh
    - tools/cleanup.py
    """
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к скрипту (должен быть внутри домашней директории).",
            },
        },
        "required": ["path"],
    }

    def __init__(self) -> None:
        self._config: Config | None = None
        try:
            from config import Config
            self._config = Config()
        except Exception as exc:
            self._init_error = str(exc)

    def execute(self, path: str) -> ToolResult:
        if not self._config:
            return ToolResult(
                success=False,
                output=f"Инструмент недоступен: {self._init_error}",
            )

        allowed, resolved, error = fs_guard(path, self._config)
        if not allowed:
            return ToolResult(success=False, output=error)

        if not resolved.exists():
            return ToolResult(success=False, output=f"Скрипт не существует: {resolved}")
        if not resolved.is_file():
            return ToolResult(success=False, output=f"Не файл: {resolved}")

        # Additional script validation (no sudo/pkexec tokens already checked in fs_guard)
        # Could also check shebang for dangerous interpreters.

        try:
            # Run script with current user privileges
            result = subprocess.run(
                [str(resolved)],
                shell=False,
                capture_output=True,
                text=True,
                timeout=30.0,
                cwd=self._config.fs_root,
            )
            output_lines = []
            if result.stdout:
                output_lines.append(result.stdout.rstrip())
            if result.stderr:
                output_lines.append(f"[stderr] {result.stderr.rstrip()}")
            if result.returncode != 0:
                output_lines.append(f"Код возврата: {result.returncode}")

            return ToolResult(
                success=result.returncode == 0,
                output="\n".join(output_lines) if output_lines else "Скрипт выполнен",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="Скрипт превысил таймаут 30 секунд.",
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Не удалось выполнить скрипт: {exc}")