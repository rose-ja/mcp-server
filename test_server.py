from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class FilesystemServerTests(unittest.TestCase):
    def setUp(self) -> None:
        sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(sandbox.cleanup)
        self.sandbox = Path(sandbox.name).resolve()
        self.workspace = self.sandbox / "workspace"
        self.workspace.mkdir()
        (self.workspace / "docs").mkdir()
        (self.workspace / "README.md").write_text(
            "MCP filesystem server\n", encoding="utf-8"
        )
        (self.workspace / "docs" / "guide.txt").write_text(
            "MCP tools and resources\n", encoding="utf-8"
        )
        workspace_patch = patch.object(server, "WORKSPACE_ROOT", self.workspace)
        workspace_patch.start()
        self.addCleanup(workspace_patch.stop)

    def test_relative_path(self) -> None:
        self.assertEqual(server.validate_relative_path("README.md"), self.workspace / "README.md")

    def test_parent_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "PATH_OUTSIDE_WORKSPACE"):
            server.validate_relative_path("../secret.txt")

    def test_absolute_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "PATH_OUTSIDE_WORKSPACE"):
            server.validate_relative_path(str(self.sandbox / "secret.txt"))

    def test_empty_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_ARGUMENT"):
            server.validate_relative_path("   ")

    def test_null_byte(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_ARGUMENT"):
            server.validate_relative_path("file\x00.txt")

    def test_list_directory(self) -> None:
        entries = server.list_directory(".")
        self.assertEqual({item["name"]: item["type"] for item in entries}, {"README.md": "file", "docs": "directory"})

    def test_list_rejects_file(self) -> None:
        with self.assertRaisesRegex(NotADirectoryError, "TARGET_TYPE_MISMATCH"):
            server.list_directory("README.md")

    def test_read_file(self) -> None:
        self.assertEqual(server.read_file("README.md"), "MCP filesystem server\n")

    def test_read_rejects_directory(self) -> None:
        with self.assertRaisesRegex(IsADirectoryError, "TARGET_TYPE_MISMATCH"):
            server.read_file("docs")

    def test_missing_file(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "TARGET_NOT_FOUND"):
            server.read_file("missing.txt")

    def test_large_file(self) -> None:
        (self.workspace / "large.txt").write_bytes(b"x" * 9)
        with patch.object(server, "MAX_READ_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "FILE_TOO_LARGE"):
                server.read_file("large.txt")

    def test_invalid_encoding(self) -> None:
        (self.workspace / "binary.dat").write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, "INVALID_FILE_ENCODING"):
            server.read_file("binary.dat")

    def test_write_file(self) -> None:
        content = "created by test\n"
        result = server.write_file("notes.txt", content)
        self.assertEqual(result["path"], "notes.txt")
        self.assertEqual(result["bytes_written"], len(content.encode("utf-8")))
        self.assertEqual((self.workspace / "notes.txt").read_text(encoding="utf-8"), content)
        self.assertFalse((self.sandbox / "notes.txt").exists())

    def test_write_traversal_has_no_side_effect(self) -> None:
        outside = self.sandbox / "outside.txt"
        with self.assertRaisesRegex(ValueError, "PATH_OUTSIDE_WORKSPACE"):
            server.write_file("../outside.txt", "must not be written")
        self.assertFalse(outside.exists())

    def test_write_preserves_outside_file(self) -> None:
        outside = self.sandbox / "outside.txt"
        outside.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "PATH_OUTSIDE_WORKSPACE"):
            server.write_file("../outside.txt", "replacement")
        self.assertEqual(outside.read_text(encoding="utf-8"), "original")

    def test_write_rejects_directory(self) -> None:
        with self.assertRaisesRegex(IsADirectoryError, "TARGET_TYPE_MISMATCH"):
            server.write_file("docs", "text")
        self.assertTrue((self.workspace / "docs").is_dir())

    def test_write_requires_existing_parent(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "TARGET_NOT_FOUND"):
            server.write_file("missing/notes.txt", "text")
        self.assertFalse((self.workspace / "missing").exists())

    def test_search_results(self) -> None:
        result = server.search_files("MCP", ".")
        self.assertEqual({(item["path"], item["line"], item["text"]) for item in result}, {("README.md", 1, "MCP filesystem server"), ("docs/guide.txt", 1, "MCP tools and resources")})

    def test_empty_query(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_ARGUMENT"):
            server.search_files("   ", ".")

    def test_search_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "PATH_OUTSIDE_WORKSPACE"):
            server.search_files("MCP", "../")

    def test_search_limit(self) -> None:
        with patch.object(server, "MAX_SEARCH_RESULTS", 1):
            self.assertEqual(len(server.search_files("MCP", ".")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
