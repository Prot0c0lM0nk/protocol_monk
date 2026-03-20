from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(slots=True)
class ProcessExecutionResult:
    returncode: int
    stdout: str
    stderr: str


def _decode_stream(data: bytes | None) -> str:
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


async def _terminate_process(
    process: asyncio.subprocess.Process,
    *,
    grace_period_seconds: float = 0.25,
) -> None:
    if process.returncode is not None:
        return

    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        process.terminate()

    try:
        await asyncio.wait_for(process.wait(), timeout=grace_period_seconds)
        return
    except asyncio.TimeoutError:
        pass

    if process.returncode is not None:
        return

    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    else:
        process.kill()

    await process.wait()


def _subprocess_kwargs(cwd: Path) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    return kwargs


async def run_shell_command(
    command: str,
    *,
    cwd: Path,
    timeout_seconds: float | None = None,
) -> ProcessExecutionResult:
    process = await asyncio.create_subprocess_shell(
        command,
        **_subprocess_kwargs(cwd),
    )
    try:
        if timeout_seconds is None:
            stdout, stderr = await process.communicate()
        else:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
    except asyncio.TimeoutError:
        await _terminate_process(process)
        raise
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise

    return ProcessExecutionResult(
        returncode=process.returncode or 0,
        stdout=_decode_stream(stdout),
        stderr=_decode_stream(stderr),
    )


async def run_exec_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float | None = None,
) -> ProcessExecutionResult:
    argv = [str(part) for part in command]
    process = await asyncio.create_subprocess_exec(
        *argv,
        **_subprocess_kwargs(cwd),
    )
    try:
        if timeout_seconds is None:
            stdout, stderr = await process.communicate()
        else:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
    except asyncio.TimeoutError:
        await _terminate_process(process)
        raise
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise

    return ProcessExecutionResult(
        returncode=process.returncode or 0,
        stdout=_decode_stream(stdout),
        stderr=_decode_stream(stderr),
    )
