"""tmux session management for reva agents."""

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from reva.launch_script import write_launch_files

SESSION_PREFIX = "reva_"


def _tmux_bin() -> str:
    path = shutil.which("tmux")
    if path is None:
        raise RuntimeError("tmux is not installed. Install it with: apt install tmux")
    return path


# Pure-bash timeout function injected into every generated launch script.
# Works on any POSIX system — no external 'timeout' binary needed.
#
# Sends SIGTERM first, then escalates to SIGKILL after a 10s grace period so
# that backends which ignore or are slow to handle SIGTERM (e.g. codex when
# wedged mid-tool-call) can't keep `wait` blocked indefinitely. Matches the
# behavior of GNU coreutils `timeout`.
_BASH_TIMEOUT_FUNC = """\
_timeout() {
    # Usage: _timeout SECONDS COMMAND [ARGS...]
    local secs=$1; shift
    "$@" &
    local pid=$!
    (
        sleep "$secs"
        kill -TERM "$pid" 2>/dev/null
        sleep 10
        kill -KILL "$pid" 2>/dev/null
    ) &
    local watcher=$!
    wait "$pid"
    local rc=$?
    kill "$watcher" 2>/dev/null
    wait "$watcher" 2>/dev/null
    return $rc
}
"""


# Loads per-agent secrets into the environment before each invocation.
#
# Two sources, in order (later overrides earlier so explicit files win):
#   1. .env — plain `KEY=value` lines (shell-safe, `#` comments allowed).
#            Sourced into the environment with `set -a`.
#            Use this for backend API keys: GEMINI_API_KEY, OPENAI_API_KEY,
#            ANTHROPIC_API_KEY, GOOGLE_API_KEY, etc.
#   2. .api_key — legacy file holding just the Koala Science API key.
#            Auto-exported as COALESCENCE_API_KEY (env var name matches
#            the Python SDK convention — the SDK package is still named
#            `coalescence`).
#
# Both files are per-agent, live in the agent directory, and NEVER get
# committed (agents_dir is gitignored). Nothing is written to the user's
# shell profile or ~/.config.
_LOAD_AGENT_ENV_FUNC = """\
_load_agent_env() {
    if [ -f .env ]; then
        set -a
        . ./.env
        set +a
    fi
    if [ -f .api_key ]; then
        COALESCENCE_API_KEY=$(tr -d '\\r\\n' < .api_key)
        export COALESCENCE_API_KEY
    fi
}
"""

# Backward-compat alias so any external callers that imported the old name
# still work.
_LOAD_AGENT_API_KEY_FUNC = _LOAD_AGENT_ENV_FUNC


# Loop-tail logic shared by both the duration-bounded and indefinite branches.
#
# Three exit-handling cases:
#   1. QUOTA_EXHAUSTED in recent log tail → sleep 1h. The Gemini OAuth /
#      free-tier quota resets on a multi-hour cadence; rapid 5s retries on a
#      429 send hundreds of failed requests that can extend Google's
#      cooldown (observed 2026-04-25). Reset the fast-fail counter since the
#      cause is external, not a flaky backend.
#   2. Fast crash (rc != 0 AND ran < 30s) → exponential backoff
#      (5 → 30 → 120 → 300s). Protects against a wedged backend that exits
#      immediately on launch. Caller can recover without manual stop.
#   3. Anything else (graceful exit, SESSION_TIMEOUT kill, run > 30s) →
#      default 5s sleep and reset the counter. Keeps normal cycling fast.
_LOOP_TAIL_LOGIC = """\
    EXIT_CODE=$?
    RUN_DURATION=$(( $(date +%s) - RUN_START_TS ))
    if tail -c 8192 agent.log 2>/dev/null | grep -q "QUOTA_EXHAUSTED"; then
        echo "[reva] QUOTA_EXHAUSTED detected, sleeping 3600s before retry..."
        sleep 3600
        CONSECUTIVE_FAST_FAILS=0
        continue
    fi
    if [ $EXIT_CODE -ne 0 ] && [ $RUN_DURATION -lt 30 ]; then
        CONSECUTIVE_FAST_FAILS=$((CONSECUTIVE_FAST_FAILS + 1))
        case $CONSECUTIVE_FAST_FAILS in
            1) BACKOFF=5 ;;
            2) BACKOFF=30 ;;
            3) BACKOFF=120 ;;
            *) BACKOFF=300 ;;
        esac
        echo "[reva] fast crash (rc=$EXIT_CODE, ${RUN_DURATION}s), backoff=${BACKOFF}s (fail #${CONSECUTIVE_FAST_FAILS})"
        sleep $BACKOFF
    else
        CONSECUTIVE_FAST_FAILS=0
        echo "[reva] agent exited ($EXIT_CODE) after ${RUN_DURATION}s, restarting in 5s..."
        sleep 5
    fi
"""


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_tmux_bin()] + args,
        capture_output=True,
        text=True,
        check=check,
    )


def session_name(agent_name: str) -> str:
    return f"{SESSION_PREFIX}{agent_name}"


def has_session(agent_name: str) -> bool:
    result = _run(["has-session", "-t", session_name(agent_name)], check=False)
    return result.returncode == 0


_EXTRACT_SESSION_ID_FROM_LOG = """\
    tail -c "+$((OFFSET+1))" agent.log | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        if d.get('type') == 'system' and d.get('subtype') == 'init' and 'session_id' in d:
            print(d['session_id'])
            break
    except Exception:
        pass
" > last_session_id 2>/dev/null"""


def _make_run_block(
    backend_command: str,
    resume_command: str | None,
    timeout_expr: str,
    session_id_extractor: str | None = None,
) -> str:
    """Return a bash snippet that runs one agent invocation with optional resume.

    Two resume patterns are supported:
    - Session ID resume ($SESSION_ID in resume_command): reads/writes last_session_id.
      The ID is extracted from agent.log (default for claude-code) or via a
      backend-supplied session_id_extractor shell command (e.g. opencode).
    - Simple resume (no $SESSION_ID): uses a .reva_has_run sentinel to detect
      whether the first invocation has already completed (e.g. gemini-cli, codex).
    """
    if resume_command is None:
        return f"""\
    _load_agent_env
    _timeout "{timeout_expr}" {backend_command}"""

    if "$SESSION_ID" in resume_command:
        # Session ID resume — fall back to fresh start if resume fails
        # (e.g. session ended normally, not deferred)
        if session_id_extractor:
            extract = f"    {session_id_extractor} > last_session_id 2>/dev/null"
        else:
            extract = _EXTRACT_SESSION_ID_FROM_LOG
        return f"""\
    _load_agent_env
    OFFSET=$(wc -c < agent.log 2>/dev/null || echo 0)
    if [ -f last_session_id ] && [ -s last_session_id ]; then
        SESSION_ID=$(cat last_session_id)
        _timeout "{timeout_expr}" {resume_command}
        RESUME_RC=$?
        if [ $RESUME_RC -ne 0 ]; then
            echo "[reva] resume failed (rc=$RESUME_RC), starting fresh session..."
            rm -f last_session_id
            _timeout "{timeout_expr}" {backend_command}
        fi
    else
        _timeout "{timeout_expr}" {backend_command}
    fi
{extract}"""
    else:
        # Simple resume: sentinel file tracks whether first run has completed
        return f"""\
    _load_agent_env
    if [ -f .reva_has_run ]; then
        _timeout "{timeout_expr}" {resume_command}
    else
        _timeout "{timeout_expr}" {backend_command}
        touch .reva_has_run
    fi"""


def build_launch_script(
    backend_command: str,
    duration_hours: float | None = None,
    session_timeout: int = 600,
    resume_command: str | None = None,
    session_id_extractor: str | None = None,
) -> str:
    """Build a bash script that runs the backend in a restart loop.

    Args:
        backend_command: Shell command to run the agent (first invocation).
        duration_hours: Total hours to run. None = indefinite.
        session_timeout: Max seconds per invocation. Kills idle backends
            (e.g. codex) that don't exit on their own, forcing a restart.
            Default: 600s (10 min).
        resume_command: If provided, used instead of backend_command after the
            first run. See _make_run_block for the two supported patterns.
        session_id_extractor: Shell command whose stdout is the session ID.
            Only used when resume_command contains $SESSION_ID and the ID
            cannot be parsed from agent.log (e.g. opencode).
    """
    if duration_hours is not None:
        timeout_secs = int(duration_hours * 3600)
        run_block = _make_run_block(backend_command, resume_command, "${PER_RUN}", session_id_extractor)
        return f"""\
#!/usr/bin/env bash
set -o pipefail
{_BASH_TIMEOUT_FUNC}
{_LOAD_AGENT_API_KEY_FUNC}
TIMEOUT={timeout_secs}
SESSION_TIMEOUT={session_timeout}
START=$(date +%s)
CONSECUTIVE_FAST_FAILS=0

while true; do
    ELAPSED=$(( $(date +%s) - START ))
    [ $ELAPSED -ge $TIMEOUT ] && echo "[reva] duration reached, stopping." && break
    REMAINING=$((TIMEOUT - ELAPSED))
    # cap each invocation at SESSION_TIMEOUT so idle backends get cycled
    PER_RUN=$((REMAINING < SESSION_TIMEOUT ? REMAINING : SESSION_TIMEOUT))
    RUN_START_TS=$(date +%s)

{run_block}
{_LOOP_TAIL_LOGIC}done
"""
    else:
        run_block = _make_run_block(backend_command, resume_command, "${SESSION_TIMEOUT}", session_id_extractor)
        return f"""\
#!/usr/bin/env bash
set -o pipefail
{_BASH_TIMEOUT_FUNC}
{_LOAD_AGENT_API_KEY_FUNC}
SESSION_TIMEOUT={session_timeout}
CONSECUTIVE_FAST_FAILS=0

while true; do
    RUN_START_TS=$(date +%s)
{run_block}
{_LOOP_TAIL_LOGIC}done
"""


def create_session(
    agent_name: str,
    working_dir: str,
    launch_script: str,
) -> None:
    """Create a detached tmux session running the launch script.

    Writes the script to a file in the agent directory so tmux can execute it
    reliably, and forwards the current environment into the session.
    """
    name = session_name(agent_name)
    if has_session(agent_name):
        raise RuntimeError(f"tmux session {name!r} already exists. Kill it first.")

    working_dir = str(Path(working_dir).resolve())
    script_path = write_launch_files(working_dir, launch_script)

    # create session then send-keys (not bash -c) so the shell is interactive
    # and properly attached to the PTY — some backends (gemini-cli) get
    # suspended (SIGTTIN) if they aren't the foreground process group leader.
    _run([
        "new-session", "-d",
        "-s", name,
        "-c", working_dir,
    ])
    _run(["send-keys", "-t", name, f"bash {script_path}; exit", "Enter"])


def kill_session(agent_name: str) -> bool:
    """Kill a tmux session. Returns True if it existed."""
    if not has_session(agent_name):
        return False
    _run(["kill-session", "-t", session_name(agent_name)])
    return True


@dataclass
class SessionInfo:
    agent_name: str
    session: str
    created: datetime | None


def list_sessions() -> list[SessionInfo]:
    """List all reva.* tmux sessions."""
    result = _run(["ls", "-F", "#{session_name}\t#{session_created}"], check=False)
    if result.returncode != 0:
        return []

    sessions = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        name, created_ts = parts
        if not name.startswith(SESSION_PREFIX):
            continue

        agent_name = name[len(SESSION_PREFIX):]
        try:
            created = datetime.fromtimestamp(int(created_ts), tz=timezone.utc)
        except (ValueError, OSError):
            created = None

        sessions.append(SessionInfo(
            agent_name=agent_name,
            session=name,
            created=created,
        ))

    return sessions


def kill_all_sessions() -> int:
    """Kill all reva.* sessions. Returns count killed."""
    sessions = list_sessions()
    for s in sessions:
        _run(["kill-session", "-t", s.session], check=False)
    return len(sessions)
