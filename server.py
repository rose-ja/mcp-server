from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer


MAX_READ_BYTES = 1 * 1024 * 1024
MAX_SEARCH_FILE_BYTES = 1 * 1024 * 1024
MAX_SEARCH_RESULTS = 100


def get_workspace_root() -> Path:
    """获取并规范化工作区根目录。"""
    configured_root = os.environ.get("MCP_WORKSPACE_ROOT")

    if configured_root:
        workspace_root = Path(configured_root).expanduser()
    else:
        workspace_root = Path(__file__).with_name("workspace")

    workspace_root = workspace_root.resolve()

    if not workspace_root.exists():
        raise RuntimeError(f"workspace root does not exist: {workspace_root}")

    if not workspace_root.is_dir():
        raise RuntimeError(f"workspace root is not a directory: {workspace_root}")

    return workspace_root


WORKSPACE_ROOT = get_workspace_root()
mcp = MCPServer("secure-filesystem-server")


def validate_relative_path(path: str) -> Path:
    """将用户输入解析为工作区内的安全路径。"""
    if not isinstance(path, str):
        raise ValueError("INVALID_ARGUMENT: path must be a string")

    normalized_path = path.strip()
    if not normalized_path:
        raise ValueError("INVALID_ARGUMENT: path must not be empty")

    if "\x00" in normalized_path:
        raise ValueError("INVALID_ARGUMENT: path contains a null byte")

    requested_path = Path(normalized_path)
    if requested_path.is_absolute():
        raise ValueError(
            "PATH_OUTSIDE_WORKSPACE: absolute paths are not allowed"
        )

    candidate_path = (WORKSPACE_ROOT / requested_path).resolve()

    try:
        candidate_path.relative_to(WORKSPACE_ROOT)
    except ValueError as error:
        raise ValueError(
            "PATH_OUTSIDE_WORKSPACE: path escapes the workspace"
        ) from error

    return candidate_path


def to_workspace_relative(path: Path) -> str:
    """将内部绝对路径转换为工作区相对路径。"""
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def ensure_existing_file(path: Path) -> None:
    """确认目标存在且是普通文件。"""
    if not path.exists():
        raise FileNotFoundError("TARGET_NOT_FOUND: file does not exist")

    if not path.is_file():
        raise IsADirectoryError("TARGET_TYPE_MISMATCH: expected a regular file")


def ensure_existing_directory(path: Path) -> None:
    """确认目标存在且是目录。"""
    if not path.exists():
        raise FileNotFoundError("TARGET_NOT_FOUND: directory does not exist")

    if not path.is_dir():
        raise NotADirectoryError("TARGET_TYPE_MISMATCH: expected a directory")


@mcp.tool()
def list_directory(path: str = ".") -> list[dict[str, Any]]:
    """列出工作区内目录的直接子项。"""
    directory_path = validate_relative_path(path)
    ensure_existing_directory(directory_path)

    entries: list[dict[str, Any]] = []

    try:
        children = sorted(directory_path.iterdir(), key=lambda item: item.name.lower())
        for entry in children:
            resolved_entry = entry.resolve()

            try:
                resolved_entry.relative_to(WORKSPACE_ROOT)
            except ValueError as error:
                raise PermissionError(
                    "PATH_OUTSIDE_WORKSPACE: directory contains an entry outside the workspace"
                ) from error

            entries.append(
                {
                    "name": entry.name,
                    "path": to_workspace_relative(resolved_entry),
                    "type": "directory" if entry.is_dir() else "file",
                }
            )
    except OSError as error:
        raise PermissionError(
            "PERMISSION_DENIED: directory cannot be read"
        ) from error

    return entries


@mcp.tool()
def read_file(path: str) -> str:
    """读取工作区内的 UTF-8 文本文件。"""
    file_path = validate_relative_path(path)
    ensure_existing_file(file_path)

    try:
        file_size = file_path.stat().st_size
    except OSError as error:
        raise PermissionError(
            "PERMISSION_DENIED: file metadata cannot be read"
        ) from error

    if file_size > MAX_READ_BYTES:
        raise ValueError(f"FILE_TOO_LARGE: file exceeds {MAX_READ_BYTES} bytes")

    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("INVALID_FILE_ENCODING: file is not valid UTF-8 text") from error
    except OSError as error:
        raise PermissionError("PERMISSION_DENIED: file cannot be read") from error


@mcp.tool()
def write_file(path: str, content: str) -> dict[str, Any]:
    """写入工作区内的 UTF-8 文本文件。"""
    if not isinstance(content, str):
        raise ValueError("INVALID_ARGUMENT: content must be a string")

    file_path = validate_relative_path(path)
    ensure_existing_directory(file_path.parent)

    if file_path.exists() and file_path.is_dir():
        raise IsADirectoryError(
            "TARGET_TYPE_MISMATCH: cannot write to a directory"
        )

    try:
        file_path.write_text(content, encoding="utf-8", newline="")
    except OSError as error:
        raise PermissionError("PERMISSION_DENIED: file cannot be written") from error

    return {
        "path": to_workspace_relative(file_path),
        "bytes_written": len(content.encode("utf-8")),
    }


@mcp.tool()
def search_files(query: str, path: str = ".") -> list[dict[str, Any]]:
    """在工作区内递归搜索 UTF-8 文本文件内容。"""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("INVALID_ARGUMENT: query must not be empty")

    search_root = validate_relative_path(path)
    ensure_existing_directory(search_root)
    results: list[dict[str, Any]] = []

    for current_path in search_root.rglob("*"):
        if len(results) >= MAX_SEARCH_RESULTS:
            break

        # 只有普通文件才读取；目录应继续遍历但不能按文件读取。
        if not current_path.is_file():
            continue

        resolved_path = current_path.resolve()
        try:
            resolved_path.relative_to(WORKSPACE_ROOT)
        except ValueError:
            continue

        try:
            if resolved_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            content = resolved_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            if query in line:
                results.append(
                    {
                        "path": to_workspace_relative(resolved_path),
                        "line": line_number,
                        "text": line,
                    }
                )

                if len(results) >= MAX_SEARCH_RESULTS:
                    break

    return results


if __name__ == "__main__":
    # stdio 的 stdout 用于 MCP 协议消息，不要使用 print 输出调试信息。
    mcp.run(transport="stdio")
