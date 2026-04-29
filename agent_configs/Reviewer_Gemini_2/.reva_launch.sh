source /home/babon7/projects/peer-review-agents/agent_configs/Reviewer_Gemini_2/.reva_env.sh
rm -f /home/babon7/projects/peer-review-agents/agent_configs/Reviewer_Gemini_2/.reva_env.sh
#!/usr/bin/env bash
set -o pipefail
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

_load_agent_env() {
    if [ -f .env ]; then
        set -a
        . ./.env
        set +a
    fi
    if [ -f .api_key ]; then
        COALESCENCE_API_KEY=$(tr -d '\r\n' < .api_key)
        export COALESCENCE_API_KEY
    fi
}

SESSION_TIMEOUT=600

while true; do
    _load_agent_env
    _timeout "${SESSION_TIMEOUT}" gemini --yolo --skip-trust -p "$(cat initial_prompt.txt)" 2>&1 | tee -a agent.log
    EXIT_CODE=$?
    echo "[reva] agent exited ($EXIT_CODE), restarting in 5s..."
    sleep 5
done
