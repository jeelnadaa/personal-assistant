"""Shell command execution tools for PowerShell and Command Prompt on Windows."""

import subprocess
from jarvis.config import config
from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool


@tool(
    name="run_command",
    description=(
        "Executes a command line instruction using PowerShell or cmd. "
        "Always requires explicit user confirmation unless allowed by configuration. Captures stdout and stderr."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command string to execute."},
            "shell": {
                "type": "string",
                "enum": ["powershell", "cmd"],
                "description": "Shell environment to use (default: powershell).",
                "default": "powershell",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 30).",
                "default": 30,
            },
        },
        "required": ["command"],
    },
    dangerous=True,
    category="shell",
)
def run_command(command: str, shell: str = "powershell", timeout: int = 30) -> ToolResult:
    """Executes shell command with timeout and output capture."""
    cmd = command.strip()
    use_ps = shell.lower() == "powershell"
    shell_args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd] if use_ps else ["cmd.exe", "/c", cmd]

    try:
        proc = subprocess.run(
            shell_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        retcode = proc.returncode

        output_parts = []
        if stdout:
            output_parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            output_parts.append(f"STDERR:\n{stderr}")
        if not output_parts:
            output_parts.append(f"Process exited with code {retcode} (no output).")
        else:
            output_parts.append(f"Exit code: {retcode}")

        combined = "\n".join(output_parts)
        if len(combined) > 2000:
            combined = combined[:1997] + "..."

        ok = (retcode == 0)
        return ToolResult(ok=ok, output=combined)

    except subprocess.TimeoutExpired:
        logger.warning("Shell command timed out after %d seconds: %s", timeout, cmd)
        return ToolResult(ok=False, output=f"Command timed out after {timeout} seconds.")
    except Exception as e:
        logger.error("Failed to execute shell command '%s': %s", cmd, e)
        return ToolResult(ok=False, output=f"Execution error: {str(e)}")
