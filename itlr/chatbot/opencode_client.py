"""Thin wrapper around the `opencode` CLI."""
import shutil
import subprocess


def get_ai_response(prompt: str, model: str = "freemodel/gpt-5.5") -> str:
    exe = shutil.which("opencode")
    if exe is None:
        raise RuntimeError("Không tìm thấy CLI 'opencode' trong PATH")

    result = subprocess.run(
        [exe, "run", "-m", model, prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "OpenCode call failed")

    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.strip().startswith(">")
    ]
    return "\n".join(lines).strip()
