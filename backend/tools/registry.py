"""
🛠️ Cherry's Tool Registry
Coding agent ke tools — file ops, search, shell, etc.
"""

import os
import re
import json
import subprocess
import shlex
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


# Default working directory
WORK_DIR = os.getenv("CHERRY_WORK_DIR", os.getcwd())


# ============================================================
# 🔒 SAFETY CONFIG
# ============================================================
DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-rf?\b", r"\brm\s+-fr?\b",
    r"\bdrop\s+(table|database)\b",
    r"\btruncate\s+table\b",
    r":\(\)\{:\|:&\};:",
    r"wget\s+.*\|\s*sh", r"curl\s+.*\|\s*sh",
    r">\s*/dev/sd", r">\s*/dev/hd",
    r"\bmkfs\b", r"\bformat\s+[a-z]:",
    r"\bshutdown\b", r"\breboot\b", r"\bhalt\b", r"\bpoweroff\b",
    r"\binit\s+0\b", r"\binit\s+6\b",
    r"\bdd\s+if=.*of=/dev/",
    r"\bchmod\s+-R\s+777\s+/\b",
    r"\bchown\s+-R\s+.*\s+/\b",
]

SAFE_READ_COMMANDS = [
    "ls", "cat", "head", "tail", "less", "more",
    "grep", "rg", "find", "tree", "file", "stat",
    "wc", "du", "df", "free", "ps", "top", "htop",
    "git status", "git log", "git diff", "git branch", "git show",
    "pwd", "whoami", "date", "uname", "hostname",
    "echo", "printf", "which", "type", "env", "printenv",
    "npm list", "pip list", "pip show", "python --version", "node --version",
    "curl -s", "wget -q",
]


def is_destructive(command: str) -> bool:
    cmd_lower = command.lower()
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True
    return False


def is_safe_read_only(command: str) -> bool:
    cmd_lower = command.lower().strip()
    return any(cmd_lower.startswith(op) for op in SAFE_READ_COMMANDS)


# ============================================================
# 🛠️ TOOL DEFINITIONS (OpenAI-compatible)
# ============================================================
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Use this to see what code looks like before editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "start_line": {"type": "integer", "description": "Optional: start reading from this line (1-based)"},
                    "end_line": {"type": "integer", "description": "Optional: stop reading at this line"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing file. Use this for new files or complete rewrites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file"},
                    "content": {"type": "string", "description": "Full content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit a specific part of a file. Finds old_text and replaces with new_text. The old_text must match exactly once. Use this for surgical edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file"},
                    "old_text": {"type": "string", "description": "Exact text to find (must match exactly once)"},
                    "new_text": {"type": "string", "description": "Text to replace it with"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a regex pattern in files. Returns matching lines with file paths and line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory to search in (default: current dir)"},
                    "file_pattern": {"type": "string", "description": "Optional: glob like '*.py' to limit file types"},
                    "max_results": {"type": "integer", "description": "Max results to return (default 50)"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Find files matching a glob pattern. Like '*.py' or '**/test_*.py'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern"},
                    "path": {"type": "string", "description": "Directory to search in"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to list (default: current)"},
                    "show_hidden": {"type": "boolean", "description": "Show hidden files (default false)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command. SAFE for read-only commands (ls, cat, grep, git status). DESTRUCTIVE commands (rm, docker stop) require explicit user confirmation before running.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch content from a URL. Use for documentation lookups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "prompt": {"type": "string", "description": "What to extract from the page"}
                },
                "required": ["url"]
            }
        }
    }
]


# ============================================================
# Tool implementations
# ============================================================
def read_file(path, start_line=None, end_line=None):
    try:
        from pathlib import Path
        fp = Path(path).expanduser().resolve()
        if not fp.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not fp.is_file():
            return {"success": False, "error": f"Not a file: {path}"}
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        sl = start_line if start_line is not None else 1
        el = end_line if end_line is not None else total
        return {"success": True, "path": str(fp), "total_lines": total,
                "start_line": sl, "end_line": min(total, el),
                "content": "".join(lines[max(0, sl-1):min(total, el)])}
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path, content):
    try:
        from pathlib import Path
        fp = Path(path).expanduser().resolve()
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "path": str(fp),
                "bytes_written": len(content), "lines_written": content.count(chr(10))+1}
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def edit_file(path, old_text, new_text):
    try:
        from pathlib import Path
        fp = Path(path).expanduser().resolve()
        if not fp.exists():
            return {"success": False, "error": f"File not found: {path}"}
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        count = content.count(old_text)
        if count == 0:
            return {"success": False, "error": "old_text not found. Check indentation."}
        if count > 1:
            return {"success": False, "error": f"old_text matches {count} places. Add more context."}
        new_content = content.replace(old_text, new_text)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {"success": True, "path": str(fp),
                "old_length": len(old_text), "new_length": len(new_text),
                "diff_lines": new_text.count(chr(10))-old_text.count(chr(10))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_code(pattern, path=None, file_pattern=None, max_results=50):
    import re
    try:
        from pathlib import Path
        sd = Path(path or WORK_DIR).expanduser().resolve()
        if not sd.exists():
            return {"success": False, "error": f"Directory not found: {sd}"}
        rg = re.compile(pattern)
        results = []
        skip = {".git", "node_modules", "__pycache__", ".next", "venv", "dist", "build", ".cache"}
        if file_pattern:
            files = list(sd.rglob(file_pattern))
        else:
            files = [p for p in sd.rglob("*") if p.is_file() and not any(d in p.parts for d in skip)]
        fs = 0
        for f in files:
            if len(results) >= max_results: break
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    for ln, line in enumerate(fh, 1):
                        if rg.search(line):
                            results.append({"file": str(f.relative_to(sd)), "line": ln, "content": line.rstrip()[:300]})
                            if len(results) >= max_results: break
                fs += 1
            except: continue
        return {"success": True, "pattern": pattern, "searched": str(sd), "files_searched": fs, "matches": results, "total": len(results)}
    except re.error as e:
        return {"success": False, "error": f"Invalid regex: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_files(pattern, path=None):
    try:
        from pathlib import Path
        sd = Path(path or WORK_DIR).expanduser().resolve()
        if not sd.exists():
            return {"success": False, "error": f"Directory not found: {sd}"}
        matches = []
        skip = {".git", "node_modules", "__pycache__", ".next", "venv", "dist", "build"}
        for m in sd.rglob(pattern):
            if not any(d in m.parts for d in skip):
                matches.append(str(m.relative_to(sd)))
                if len(matches) >= 200: break
        return {"success": True, "pattern": pattern, "matches": matches, "total": len(matches)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_dir(path=None, show_hidden=False):
    try:
        from pathlib import Path
        t = Path(path or WORK_DIR).expanduser().resolve()
        if not t.exists(): return {"success": False, "error": f"Not found: {t}"}
        if not t.is_dir(): return {"success": False, "error": f"Not a dir: {t}"}
        items = []
        for i in sorted(t.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if not show_hidden and i.name.startswith("."): continue
            items.append({"name": i.name, "type": "dir" if i.is_dir() else "file",
                          "size": i.stat().st_size if i.is_file() else None})
        return {"success": True, "path": str(t), "items": items, "count": len(items)}
    except Exception as e:
        return {"success": False, "error": str(e)}



def run_command(command, timeout=30):
    import subprocess
    try:
        if is_destructive(command):
            return {"success": False, "error": "BLOCKED: Destructive. Confirm with haan kar de.", "requires_confirmation": True, "command": command}
        if is_safe_read_only(command):
            timeout = min(timeout, 30)
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=WORK_DIR)
        return {"success": proc.returncode == 0, "command": command, "stdout": proc.stdout,
                "stderr": proc.stderr, "exit_code": proc.returncode, "timestamp": datetime.now().isoformat()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout after {timeout}s", "command": command}
    except Exception as e:
        return {"success": False, "error": str(e), "command": command}


def web_fetch(url, prompt=""):
    try:
        import requests
        r = requests.get(url, timeout=15, headers={"User-Agent": "Cherry/1.0"})
        return {"success": r.status_code == 200, "url": url, "status": r.status_code,
                "content": r.text[:10000], "length": len(r.text)}
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


TOOL_REGISTRY = {
    "read_file": read_file, "write_file": write_file, "edit_file": edit_file,
    "search_code": search_code, "find_files": find_files, "list_dir": list_dir,
    "run_command": run_command, "web_fetch": web_fetch,
}


def execute_tool(name, arguments):
    if name not in TOOL_REGISTRY:
        return {"success": False, "error": f"Unknown tool: {name}"}
    try:
        return TOOL_REGISTRY[name](**arguments)
    except TypeError as e:
        return {"success": False, "error": f"Invalid args for {name}: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Tool {name} failed: {e}"}


def get_tool_definitions():
    return TOOL_DEFINITIONS
