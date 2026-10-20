"""Filesystem and directory management tools for Windows 11."""

from datetime import datetime
import os
from pathlib import Path
import shutil
import send2trash

from jarvis.config import config
from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool


def _resolve_safe_path(path_str: str) -> Path:
    """Expands user tilde and environment variables to an absolute Path."""
    expanded = os.path.expandvars(path_str.strip())
    return Path(expanded).expanduser().resolve()


def _is_protected(path: Path) -> bool:
    """Checks whether path falls inside protected system directories."""
    safety_cfg = config.get("safety", {})
    protected = safety_cfg.get("protected_paths", [
        r"C:\Windows",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ])
    for prot in protected:
        prot_p = Path(prot).resolve()
        if path == prot_p or prot_p in path.parents:
            return True
    return False


@tool(
    name="search_files",
    description=(
        "Searches for files matching a filename substring within a directory tree. "
        "Skips AppData, node_modules, and .git folders. Returns matched paths, sizes, and modified dates."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Filename substring to match (case-insensitive).",
            },
            "folder": {
                "type": "string",
                "description": "Folder path to search inside (e.g. '~', '~/Documents', 'C:/Projects'). Defaults to user home.",
                "default": "~",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of file matches to return (default: 15).",
                "default": 15,
            },
        },
        "required": ["query"],
    },
    dangerous=False,
    category="files",
)
def search_files(query: str, folder: str = "~", max_results: int = 15) -> ToolResult:
    """Searches directory for filename substring matches."""
    root = _resolve_safe_path(folder)
    if not root.exists() or not root.is_dir():
        return ToolResult(ok=False, output=f"Directory '{folder}' does not exist.")

    q = query.strip().lower()
    matches: list[str] = []
    skipped_names = {"appdata", "node_modules", ".git", "$recycle.bin", "__pycache__"}

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d.lower() not in skipped_names]

        for fname in filenames:
            if q in fname.lower():
                full_path = Path(dirpath) / fname
                try:
                    stat = full_path.stat()
                    size_kb = stat.st_size / 1024.0
                    mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    matches.append(f"{full_path} ({size_kb:.1f} KB, modified {mod_time})")
                except Exception:
                    matches.append(str(full_path))

                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    if not matches:
        return ToolResult(ok=True, output=f"No files found matching '{query}' in '{root}'.")

    return ToolResult(ok=True, output=f"Found {len(matches)} matches:\n" + "\n".join(matches))


@tool(
    name="read_text_file",
    description="Reads and returns the text content of a file, up to max_chars (default 5000).",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read."},
            "max_chars": {"type": "integer", "description": "Max characters to read.", "default": 5000},
        },
        "required": ["path"],
    },
    dangerous=False,
    category="files",
)
def read_text_file(path: str, max_chars: int = 5000) -> ToolResult:
    """Reads content from a UTF-8/plain text file."""
    p = _resolve_safe_path(path)
    if not p.exists() or not p.is_file():
        return ToolResult(ok=False, output=f"File not found: '{path}'")

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars + 1)
        truncated = len(content) > max_chars
        text = content[:max_chars]
        if truncated:
            text += "\n[content truncated to limit]"
        return ToolResult(ok=True, output=text)
    except Exception as e:
        return ToolResult(ok=False, output=f"Could not read file: {str(e)}")


@tool(
    name="write_text_file",
    description="Writes text content to a file. Refuses to overwrite unless overwrite is explicitly True.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target destination path."},
            "content": {"type": "string", "description": "Text content to write."},
            "overwrite": {"type": "boolean", "description": "Whether to overwrite existing file.", "default": False},
        },
        "required": ["path", "content"],
    },
    dangerous=False,
    category="files",
)
def write_text_file(path: str, content: str, overwrite: bool = False) -> ToolResult:
    """Writes text content to a destination file."""
    p = _resolve_safe_path(path)
    if p.exists() and not overwrite:
        return ToolResult(
            ok=False,
            output=f"File '{path}' already exists and overwrite is False. Specify overwrite=True to replace.",
        )

    if _is_protected(p):
        return ToolResult(ok=False, output=f"Cannot write to protected system path '{p}'.")

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult(ok=True, output=f"Successfully wrote {len(content)} characters to '{p}'.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to write file: {str(e)}")


@tool(
    name="list_folder",
    description="Lists entries (files and directories) inside a specified folder.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list."}
        },
        "required": ["path"],
    },
    dangerous=False,
    category="files",
)
def list_folder(path: str) -> ToolResult:
    """Lists directory contents with file/folder flags."""
    p = _resolve_safe_path(path)
    if not p.exists() or not p.is_dir():
        return ToolResult(ok=False, output=f"Folder '{path}' does not exist or is not a directory.")

    try:
        items = []
        for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
            kind = "[DIR]" if child.is_dir() else "[FILE]"
            items.append(f"{kind} {child.name}")
        output = f"Contents of '{p}' ({len(items)} items):\n" + "\n".join(items[:50])
        return ToolResult(ok=True, output=output)
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to list folder: {str(e)}")


@tool(
    name="open_file",
    description="Opens a file with its default registered Windows application (via os.startfile).",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path of the file to open."}
        },
        "required": ["path"],
    },
    dangerous=False,
    category="files",
)
def open_file(path: str) -> ToolResult:
    """Opens a file with the default associated application."""
    p = _resolve_safe_path(path)
    if not p.exists():
        return ToolResult(ok=False, output=f"File '{path}' does not exist.")

    try:
        os.startfile(str(p))
        return ToolResult(ok=True, output=f"Opened file with default app: '{p}'.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to open file: {str(e)}")


@tool(
    name="move_file",
    description="Moves or renames a file or directory from src to dst.",
    input_schema={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path."},
            "dst": {"type": "string", "description": "Destination path."},
        },
        "required": ["src", "dst"],
    },
    dangerous=True,
    category="files",
)
def move_file(src: str, dst: str) -> ToolResult:
    """Moves a file or directory to a new path."""
    s = _resolve_safe_path(src)
    d = _resolve_safe_path(dst)

    if not s.exists():
        return ToolResult(ok=False, output=f"Source path '{src}' does not exist.")
    if _is_protected(s) or _is_protected(d):
        return ToolResult(ok=False, output="Cannot move to or from protected system directories.")

    try:
        shutil.move(str(s), str(d))
        return ToolResult(ok=True, output=f"Moved '{s}' to '{d}'.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to move: {str(e)}")


@tool(
    name="copy_file",
    description="Copies a file or folder from src to dst.",
    input_schema={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path."},
            "dst": {"type": "string", "description": "Destination path."},
        },
        "required": ["src", "dst"],
    },
    dangerous=False,
    category="files",
)
def copy_file(src: str, dst: str) -> ToolResult:
    """Copies a file or folder to destination."""
    s = _resolve_safe_path(src)
    d = _resolve_safe_path(dst)

    if not s.exists():
        return ToolResult(ok=False, output=f"Source path '{src}' does not exist.")
    if _is_protected(d):
        return ToolResult(ok=False, output=f"Cannot copy to protected system path '{d}'.")

    try:
        if s.is_dir():
            shutil.copytree(str(s), str(d), dirs_exist_ok=True)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(s), str(d))
        return ToolResult(ok=True, output=f"Copied '{s}' to '{d}'.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to copy: {str(e)}")


@tool(
    name="delete_file",
    description="Safely deletes a file or directory by sending it to the Windows Recycle Bin (using send2trash). Never permanently deletes.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to delete."}
        },
        "required": ["path"],
    },
    dangerous=True,
    category="files",
)
def delete_file(path: str) -> ToolResult:
    """Sends file or folder to Recycle Bin."""
    p = _resolve_safe_path(path)
    if not p.exists():
        return ToolResult(ok=False, output=f"Path '{path}' does not exist.")

    if _is_protected(p):
        return ToolResult(ok=False, output=f"Refusing to delete inside protected system directory '{p}'.")

    try:
        send2trash.send2trash(str(p))
        return ToolResult(ok=True, output=f"Sent '{p}' to the Recycle Bin.")
    except Exception as e:
        logger.error("Failed to delete %s: %s", p, e)
        return ToolResult(ok=False, output=f"Failed to recycle '{p}': {str(e)}")


@tool(
    name="create_folder",
    description="Creates a new folder at the given path (including parent directories).",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to create."}
        },
        "required": ["path"],
    },
    dangerous=False,
    category="files",
)
def create_folder(path: str) -> ToolResult:
    """Creates directory tree."""
    p = _resolve_safe_path(path)
    if _is_protected(p):
        return ToolResult(ok=False, output=f"Cannot create folder in protected path '{p}'.")

    try:
        p.mkdir(parents=True, exist_ok=True)
        return ToolResult(ok=True, output=f"Created folder: '{p}'.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to create folder: {str(e)}")
