#!/usr/bin/env bash
set -u
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$(command -v python3 || command -v python || true)"
if [ -z "${PYTHON}" ]; then
  echo "python not found"
  exit 1
fi
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found"
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo "git not found"
  exit 1
fi

RUN_ID="$(date +%Y%m%d%H%M%S)-$$"
TEST_PARENT="$(cd "${ROOT}/.." && pwd)"
TEST_DIR="${TEST_PARENT}/test_ccb_fastpath_${RUN_ID}"
PROJECT="${TEST_DIR}/project"
ARTIFACT_ROOT="${TEST_DIR}/artifacts"
HOME_DIR="${ARTIFACT_ROOT}/home"
STUB_BIN="${ARTIFACT_ROOT}/bin"
STUB_PROVIDER="${ROOT}/test/stubs/provider_stub.py"
CODEX_ROOT="${ARTIFACT_ROOT}/codex"
CLAUDE_ROOT="${ARTIFACT_ROOT}/claude"
GEMINI_ROOT="${ARTIFACT_ROOT}/gemini"
OPENCODE_ROOT="${ARTIFACT_ROOT}/opencode"
DROID_ROOT="${ARTIFACT_ROOT}/droid"
TMUX_SOCKET="ccb-fastpath-${RUN_ID}"

ASK_COUNT="${CCB_FASTPATH_STRESS_ASK_COUNT:-60}"
MAX_RECEIPT_MS="${CCB_FASTPATH_STRESS_MAX_RECEIPT_MS:-2500}"
P95_RECEIPT_MS="${CCB_FASTPATH_STRESS_P95_RECEIPT_MS:-1500}"
STUB_DELAY="${CCB_FASTPATH_STRESS_STUB_DELAY:-1.5}"
if [ -n "${CCB_FASTPATH_STRESS_ASK_WAIT_TIMEOUT_S:-}" ]; then
  ASK_WAIT_TIMEOUT_S="${CCB_FASTPATH_STRESS_ASK_WAIT_TIMEOUT_S}"
else
  ASK_WAIT_TIMEOUT_S="$("${PYTHON}" - "${ASK_COUNT}" "${STUB_DELAY}" <<'PY'
import math
import sys

ask_count = max(1, int(sys.argv[1]))
stub_delay = max(0.0, float(sys.argv[2]))
per_agent_depth = math.ceil(ask_count / 3.0)

# This stress validates submit fastpath latency plus eventual serial-provider
# convergence. Deep sampled jobs need a queue-depth budget, not a submit budget.
budget = per_agent_depth * max(stub_delay + 20.0, 20.0) + 120.0
print(int(max(180.0, min(900.0, budget))))
PY
)"
fi

mkdir -p "${PROJECT}/.ccb" "${HOME_DIR}" "${STUB_BIN}" "${CODEX_ROOT}" "${CLAUDE_ROOT}" "${GEMINI_ROOT}" "${OPENCODE_ROOT}" "${DROID_ROOT}"

export HOME="${HOME_DIR}"
export PATH="${STUB_BIN}:${PATH}"
export CODEX_SESSION_ROOT="${CODEX_ROOT}"
export CLAUDE_PROJECTS_ROOT="${CLAUDE_ROOT}"
export GEMINI_ROOT
export OPENCODE_STORAGE_ROOT="${OPENCODE_ROOT}"
export DROID_SESSIONS_ROOT="${DROID_ROOT}"
export CODEX_START_CMD="${STUB_BIN}/codex"
export GEMINI_START_CMD="${STUB_BIN}/gemini"
export CLAUDE_START_CMD="${STUB_BIN}/claude"
export CCB_TMUX_SOCKET="${TMUX_SOCKET}"
export CCB_REPLY_LANG="en"
export CCB_CLAUDE_SKILLS=0
export CCB_SYNC_TIMEOUT=30
export CCB_WAIT_TIMEOUT_S=45
export CCB_WAIT_POLL_INTERVAL_S=0.1
export CCB_ASK_WAIT_TIMEOUT_S="${ASK_WAIT_TIMEOUT_S}"
export CCB_ASK_WAIT_POLL_INTERVAL_S=0.1
export CCB_WATCH_TIMEOUT_S=45
export CCB_WATCH_POLL_INTERVAL_S=0.1
export CCB_GEMINI_READY_TIMEOUT_S=0.5
export CCB_CLAUDE_READY_TIMEOUT_S=0.5
export STUB_DELAY
unset CCB_SESSION_FILE

FAIL=0
SESSIONS=()
JOBS_FILE="${PROJECT}/jobs.txt"
LATENCY_FILE="${PROJECT}/submit-latencies-ms.txt"

log() { echo "== $*"; }
ok() { echo "[OK] $*"; }
fail() { echo "[FAIL] $*"; FAIL=1; }
has_match() {
  local text="$1"
  local pattern="$2"
  grep -q -- "${pattern}" <<<"${text}"
}

q() {
  printf '%q' "$1"
}

tmux_cmd() {
  tmux -L "${TMUX_SOCKET}" "$@"
}

cleanup() {
  if [ -d "${PROJECT}" ]; then
    env HOME="${HOME}" PATH="${PATH}" CCB_TMUX_SOCKET="${CCB_TMUX_SOCKET}" "${ROOT}/ccb" --project "${PROJECT}" kill >/dev/null 2>&1 || true
  fi
  local session
  for session in "${SESSIONS[@]}"; do
    tmux_cmd kill-session -t "${session}" >/dev/null 2>&1 || true
  done
  tmux_cmd kill-server >/dev/null 2>&1 || true
}
trap cleanup EXIT

install_stub_providers() {
  local provider
  for provider in codex gemini claude opencode droid; do
    cat >"${STUB_BIN}/${provider}" <<EOF
#!/usr/bin/env bash
exec "${PYTHON}" "${STUB_PROVIDER}" --provider ${provider} "\$@"
EOF
    chmod +x "${STUB_BIN}/${provider}"
  done
}

bootstrap_tmux_server() {
  local bootstrap="fastpath-bootstrap-${RUN_ID}"
  tmux_cmd new-session -d -s "${bootstrap}" -c "${ARTIFACT_ROOT}" "sleep 3600"
  SESSIONS+=("${bootstrap}")
  tmux_cmd set-environment -g HOME "${HOME}"
  tmux_cmd set-environment -g PATH "${PATH}"
  tmux_cmd set-environment -g CODEX_SESSION_ROOT "${CODEX_SESSION_ROOT}"
  tmux_cmd set-environment -g CLAUDE_PROJECTS_ROOT "${CLAUDE_PROJECTS_ROOT}"
  tmux_cmd set-environment -g GEMINI_ROOT "${GEMINI_ROOT}"
  tmux_cmd set-environment -g OPENCODE_STORAGE_ROOT "${OPENCODE_STORAGE_ROOT}"
  tmux_cmd set-environment -g DROID_SESSIONS_ROOT "${DROID_SESSIONS_ROOT}"
  tmux_cmd set-environment -g CODEX_START_CMD "${CODEX_START_CMD}"
  tmux_cmd set-environment -g GEMINI_START_CMD "${GEMINI_START_CMD}"
  tmux_cmd set-environment -g CLAUDE_START_CMD "${CLAUDE_START_CMD}"
  tmux_cmd set-environment -g CCB_TMUX_SOCKET "${CCB_TMUX_SOCKET}"
  tmux_cmd set-environment -g CCB_GEMINI_READY_TIMEOUT_S "${CCB_GEMINI_READY_TIMEOUT_S}"
  tmux_cmd set-environment -g CCB_CLAUDE_READY_TIMEOUT_S "${CCB_CLAUDE_READY_TIMEOUT_S}"
  tmux_cmd set-environment -g STUB_DELAY "${STUB_DELAY}"
}

init_project() {
  (
    cd "${PROJECT}" || exit 1
    git init -q
    git config user.email "ccb@example.test"
    git config user.name "ccb-system"
    printf '%s\n' "# fastpath ${RUN_ID}" >README.md
    git add README.md
    git commit -qm "init"
  )
  cat >"${PROJECT}/.ccb/ccb.config" <<'EOF'
alpha:codex,beta:claude,gamma:gemini
EOF
}

start_project() {
  local session="fastpath-${RUN_ID}"
  local start_out="${PROJECT}/start.out"
  local start_err="${PROJECT}/start.err"
  local cmd
  cmd="env HOME=$(q "${HOME}") PATH=$(q "${PATH}") CODEX_SESSION_ROOT=$(q "${CODEX_SESSION_ROOT}") CLAUDE_PROJECTS_ROOT=$(q "${CLAUDE_PROJECTS_ROOT}") GEMINI_ROOT=$(q "${GEMINI_ROOT}") OPENCODE_STORAGE_ROOT=$(q "${OPENCODE_STORAGE_ROOT}") DROID_SESSIONS_ROOT=$(q "${DROID_SESSIONS_ROOT}") CODEX_START_CMD=$(q "${CODEX_START_CMD}") GEMINI_START_CMD=$(q "${GEMINI_START_CMD}") CLAUDE_START_CMD=$(q "${CLAUDE_START_CMD}") CCB_TMUX_SOCKET=$(q "${CCB_TMUX_SOCKET}") CCB_GEMINI_READY_TIMEOUT_S=$(q "${CCB_GEMINI_READY_TIMEOUT_S}") CCB_CLAUDE_READY_TIMEOUT_S=$(q "${CCB_CLAUDE_READY_TIMEOUT_S}") CCB_CLAUDE_SKILLS=0 CCB_REPLY_LANG=en STUB_DELAY=$(q "${STUB_DELAY}") $(q "${ROOT}/ccb") >$(q "${start_out}") 2>$(q "${start_err}"); exec sleep 3600"
  tmux_cmd new-session -d -s "${session}" -c "${PROJECT}" bash -lc "${cmd}"
  SESSIONS+=("${session}")
}

ccb_project() {
  env HOME="${HOME}" PATH="${PATH}" CODEX_SESSION_ROOT="${CODEX_SESSION_ROOT}" CLAUDE_PROJECTS_ROOT="${CLAUDE_PROJECTS_ROOT}" GEMINI_ROOT="${GEMINI_ROOT}" OPENCODE_STORAGE_ROOT="${OPENCODE_STORAGE_ROOT}" DROID_SESSIONS_ROOT="${DROID_ROOT}" CODEX_START_CMD="${CODEX_START_CMD}" GEMINI_START_CMD="${GEMINI_START_CMD}" CLAUDE_START_CMD="${CLAUDE_START_CMD}" CCB_TMUX_SOCKET="${CCB_TMUX_SOCKET}" CCB_GEMINI_READY_TIMEOUT_S="${CCB_GEMINI_READY_TIMEOUT_S}" CCB_CLAUDE_READY_TIMEOUT_S="${CCB_CLAUDE_READY_TIMEOUT_S}" CCB_CLAUDE_SKILLS=0 CCB_REPLY_LANG=en "${ROOT}/ccb" --project "${PROJECT}" "$@"
}

wait_for_start() {
  local start
  start="$(date +%s)"
  while [ "$(( $(date +%s) - start ))" -lt 25 ]; do
    if [ -s "${PROJECT}/start.out" ] && grep -q '^start_status: ok$' "${PROJECT}/start.out"; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

wait_for_mount() {
  local start out
  start="$(date +%s)"
  while [ "$(( $(date +%s) - start ))" -lt 25 ]; do
    out="$(ccb_project ps 2>/dev/null)" || out=""
    if has_match "${out}" '^ccbd_state: mounted$'; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

extract_job_id() {
  awk '
    /^accepted job=/ {
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^job=/) {
          job = $i
          sub(/^job=/, "", job)
          print job
          exit
        }
      }
    }
  '
}

now_ms() {
  "${PYTHON}" - <<'PY'
import time
print(int(time.time() * 1000))
PY
}

submit_one() {
  local index="$1"
  local target="$2"
  local sender="$3"
  local started ended elapsed out job_id
  local ask_args=()
  if [ "${sender}" != "user" ]; then
    ask_args+=(--silence)
  fi
  started="$(now_ms)"
  out="$(ccb_project ask "${ask_args[@]}" "${target}" from "${sender}" "fastpath-${index}-${target}")" || {
    printf '%s\n' "${out}" >"${PROJECT}/ask-${index}.err"
    fail "submit ${index} ${target}"
    return
  }
  ended="$(now_ms)"
  elapsed=$(( ended - started ))
  job_id="$(extract_job_id <<<"${out}" | head -n 1)"
  printf '%s\n' "${out}" >"${PROJECT}/ask-${index}-${target}.out"
  printf '%s\n' "${elapsed}" >>"${LATENCY_FILE}"
  if [ -z "${job_id}" ]; then
    fail "submit ${index} job id"
    return
  fi
  printf '%s %s %s\n' "${job_id}" "${target}" "${elapsed}" >>"${JOBS_FILE}"
  if [ "${elapsed}" -le "${MAX_RECEIPT_MS}" ]; then
    ok "submit ${index} ${target} receipt ${elapsed}ms"
  else
    fail "submit ${index} ${target} receipt ${elapsed}ms > ${MAX_RECEIPT_MS}ms"
  fi
}

latency_percentile() {
  local percentile="$1"
  "${PYTHON}" - "${LATENCY_FILE}" "${percentile}" <<'PY'
import math
import sys
from pathlib import Path

values = sorted(int(line.strip()) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip())
if not values:
    print(0)
    raise SystemExit
p = float(sys.argv[2])
index = max(0, min(len(values) - 1, math.ceil((p / 100.0) * len(values)) - 1))
print(values[index])
PY
}

assert_latency_summary() {
  local p50 p95 max
  p50="$(latency_percentile 50)"
  p95="$(latency_percentile 95)"
  max="$(latency_percentile 100)"
  echo "submit_latency_p50_ms: ${p50}"
  echo "submit_latency_p95_ms: ${p95}"
  echo "submit_latency_max_ms: ${max}"
  if [ "${p95}" -le "${P95_RECEIPT_MS}" ]; then
    ok "submit p95 bounded ${p95}ms"
  else
    fail "submit p95 ${p95}ms > ${P95_RECEIPT_MS}ms"
  fi
}

assert_observers() {
  local out
  out="$(ccb_project queue all)" || {
    fail "queue all"
    return
  }
  printf '%s\n' "${out}" >"${PROJECT}/queue-all.out"
  if has_match "${out}" '^queue_status: ok$'; then
    ok "queue all summary"
  else
    fail "queue all summary"
  fi
  out="$(ccb_project pend --queue all)" || {
    fail "pend queue all"
    return
  }
  printf '%s\n' "${out}" >"${PROJECT}/pend-queue-all.out"
  if has_match "${out}" 'observer_notice: weak observer surface'; then
    ok "pend queue weak observer notice"
  else
    fail "pend queue weak observer notice"
  fi
}

wait_sample_jobs() {
  local total index line job target elapsed out
  total="$(wc -l <"${JOBS_FILE}" | tr -d ' ')"
  for index in 1 "$(( total / 2 ))" "${total}"; do
    [ "${index}" -lt 1 ] && index=1
    line="$(sed -n "${index}p" "${JOBS_FILE}")"
    job="$(awk '{print $1}' <<<"${line}")"
    target="$(awk '{print $2}' <<<"${line}")"
    [ -z "${job}" ] && continue
    out="$(ccb_project pend --watch "${job}")" || {
      fail "pend watch ${target} ${job}"
      continue
    }
    printf '%s\n' "${out}" >"${PROJECT}/wait-${job}.out"
    if has_match "${out}" '^watch_status: terminal$' && has_match "${out}" '^status: completed$'; then
      ok "pend watch ${target} ${job}"
    else
      fail "pend watch ${target} ${job}"
    fi
  done
}

assert_doctor_and_kill() {
  local out
  out="$(ccb_project doctor)" || {
    fail "doctor"
    return
  }
  printf '%s\n' "${out}" >"${PROJECT}/doctor.out"
  if has_match "${out}" '^ccbd_state: mounted$' && has_match "${out}" '^ccbd_health: healthy$'; then
    ok "doctor"
  else
    fail "doctor"
  fi
  if ccb_project kill >"${PROJECT}/kill.out" 2>"${PROJECT}/kill.err"; then
    ok "kill"
  else
    fail "kill"
    return
  fi
  local start ping_out
  start="$(date +%s)"
  while [ "$(( $(date +%s) - start ))" -lt 20 ]; do
    ping_out="$(ccb_project ping ccbd 2>/dev/null)" || ping_out=""
    if has_match "${ping_out}" '^mount_state: unmounted$'; then
      ok "kill unmounted"
      return
    fi
    sleep 0.2
  done
  fail "kill unmounted"
}

run_stress() {
  local i target sender
  : >"${JOBS_FILE}"
  : >"${LATENCY_FILE}"
  log "Linux fastpath stress: asks=${ASK_COUNT} stub_delay=${STUB_DELAY}s"
  i=1
  while [ "${i}" -le "${ASK_COUNT}" ]; do
    case $(( (i - 1) % 3 )) in
      0) target="alpha"; sender="user" ;;
      1) target="beta"; sender="alpha" ;;
      *) target="gamma"; sender="beta" ;;
    esac
    submit_one "${i}" "${target}" "${sender}"
    i=$(( i + 1 ))
  done
  assert_latency_summary
  assert_observers
  wait_sample_jobs
  assert_doctor_and_kill
}

install_stub_providers
bootstrap_tmux_server
init_project
start_project
if wait_for_start && wait_for_mount; then
  ok "project start"
else
  fail "project start"
fi

if [ "${FAIL}" -eq 0 ]; then
  run_stress
fi

if [ "${FAIL}" -ne 0 ]; then
  echo "artifacts: ${PROJECT}"
  echo "FAILURES DETECTED"
  exit 1
fi

echo "artifacts: ${PROJECT}"
echo "ALL TESTS PASSED"
