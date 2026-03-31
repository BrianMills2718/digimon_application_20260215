#!/usr/bin/env bash
# Continue Plan 22 end-to-end without relying on an interactive shell:
# 1. wait for or resume the projection build,
# 2. swap the projected graph into the MuSiQue benchmark namespace,
# 3. rerun the frozen tranche under the same runtime conditions,
# 4. restore the original graph,
# 5. write a machine-readable before/after comparison artifact.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DIGIMON_PYTHON="${DIGIMON_PYTHON:-$HOME/miniconda3/envs/digimon/bin/python}"
SOURCE_DATASET="${SOURCE_DATASET:-MuSiQue}"
ARTIFACT_DATASET="${ARTIFACT_DATASET:-MuSiQue_plan22_projection}"
QUESTIONS_FILE="${QUESTIONS_FILE:-eval/fixtures/musique_canonicalization_tranche.txt}"
MODEL="${MODEL:-gemini/gemini-2.5-flash}"
QUESTION_TIMEOUT="${QUESTION_TIMEOUT:-180}"
BUILD_PID="${BUILD_PID:-}"
SLEEP_SECS="${SLEEP_SECS:-120}"
BASELINE_JSON="${BASELINE_JSON:-results/MuSiQue_gemini-2-5-flash_consolidated_20260331T225837Z.json}"
POST_TAG="${POST_TAG:-plan22_postprojection_t180}"

RESULTS_ROOT="${REPO_ROOT}/results"
SOURCE_GRAPH_DIR="${RESULTS_ROOT}/${SOURCE_DATASET}/er_graph"
ARTIFACT_GRAPH_DIR="${RESULTS_ROOT}/${ARTIFACT_DATASET}/er_graph"
CHECKPOINT_PATH="${ARTIFACT_GRAPH_DIR}/_checkpoint_processed.json"
MANIFEST_PATH="${ARTIFACT_GRAPH_DIR}/graph_build_manifest.json"
FOLLOWTHROUGH_LOG="${RESULTS_ROOT}/plan22_projection_followthrough.log"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${RESULTS_ROOT}/${SOURCE_DATASET}/er_graph_plan22_preprojection_backup_${RUN_TS}"
COMPARE_JSON="${RESULTS_ROOT}/plan22_projection_compare_${RUN_TS}.json"

log() {
  printf '[plan22-followthrough] %s\n' "$*" | tee -a "${FOLLOWTHROUGH_LOG}"
}

artifact_complete() {
  [[ -f "${MANIFEST_PATH}" && ! -f "${CHECKPOINT_PATH}" ]]
}

processed_count() {
  if [[ ! -f "${CHECKPOINT_PATH}" ]]; then
    printf '0'
    return
  fi
  python - <<'PY' "${CHECKPOINT_PATH}"
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
print(len(data))
PY
}

wait_for_existing_builder() {
  local pid="$1"
  while kill -0 "${pid}" 2>/dev/null; do
    log "waiting for existing build pid=${pid}; processed=$(processed_count)"
    sleep "${SLEEP_SECS}"
  done
  log "existing build pid=${pid} exited"
}

resume_build_if_needed() {
  while ! artifact_complete; do
    if [[ -n "${BUILD_PID}" ]] && kill -0 "${BUILD_PID}" 2>/dev/null; then
      wait_for_existing_builder "${BUILD_PID}"
      BUILD_PID=""
      continue
    fi

    log "artifact incomplete; resuming build with checkpoint support"
    (
      cd "${REPO_ROOT}"
      "${DIGIMON_PYTHON}" eval/prebuild_graph.py "${SOURCE_DATASET}" \
        --artifact-dataset-name "${ARTIFACT_DATASET}" \
        --force-rebuild \
        --graph-profile tkg \
        --enable-chunk-cooccurrence \
        --enable-passage-nodes \
        --skip-entity-vdb \
        --skip-relationship-vdb
    ) | tee -a "${FOLLOWTHROUGH_LOG}"
  done
  log "projection artifact complete: ${MANIFEST_PATH}"
}

restore_original_graph() {
  if [[ -L "${SOURCE_GRAPH_DIR}" ]]; then
    rm -f "${SOURCE_GRAPH_DIR}"
  fi
  if [[ -d "${BACKUP_DIR}" ]]; then
    mv "${BACKUP_DIR}" "${SOURCE_GRAPH_DIR}"
    log "restored original graph directory to ${SOURCE_GRAPH_DIR}"
  fi
}

swap_projection_graph_in() {
  if [[ -L "${SOURCE_GRAPH_DIR}" || ! -d "${SOURCE_GRAPH_DIR}" ]]; then
    log "refusing to swap because source graph path is not a plain directory: ${SOURCE_GRAPH_DIR}"
    exit 1
  fi
  mv "${SOURCE_GRAPH_DIR}" "${BACKUP_DIR}"
  ln -s "../${ARTIFACT_DATASET}/er_graph" "${SOURCE_GRAPH_DIR}"
  log "swapped projection graph into ${SOURCE_GRAPH_DIR} via symlink"
}

run_post_projection_benchmark() {
  local started_epoch
  started_epoch="$(date +%s)"
  (
    cd "${REPO_ROOT}"
    "${DIGIMON_PYTHON}" eval/run_agent_benchmark.py \
      --dataset "${SOURCE_DATASET}" \
      --questions-file "${QUESTIONS_FILE}" \
      --model "${MODEL}" \
      --backend direct \
      --mode hybrid \
      --disable-embedding-tools \
      --question-delay 0 \
      --timeout "${QUESTION_TIMEOUT}" \
      --agent-spec none \
      --allow-missing-agent-spec \
      --missing-agent-spec-reason "Plan22 frozen tranche rerun" \
      --post-det-checks none \
      --post-gate-policy none \
      --tag "${POST_TAG}"
  ) | tee -a "${FOLLOWTHROUGH_LOG}" >&2

  local latest_json
  latest_json="$(find "${RESULTS_ROOT}" -maxdepth 1 -type f -name "${SOURCE_DATASET}_*.json" -printf '%T@ %p\n' \
    | sort -nr \
    | awk -v start="${started_epoch}" '$1 >= start {print $2; exit}')"
  if [[ -z "${latest_json}" ]]; then
    log "could not locate post-projection benchmark json newer than ${started_epoch}"
    exit 1
  fi
  printf '%s' "${latest_json}"
}

write_comparison_json() {
  local baseline_json="$1"
  local post_json="$2"
  python - <<'PY' "${baseline_json}" "${post_json}" "${COMPARE_JSON}"
import json, pathlib, sys

baseline_path = pathlib.Path(sys.argv[1])
post_path = pathlib.Path(sys.argv[2])
out_path = pathlib.Path(sys.argv[3])

baseline = json.loads(baseline_path.read_text())
post = json.loads(post_path.read_text())

def summarize(run):
    return {
        "em": run.get("em"),
        "f1": run.get("f1"),
        "llm_em": run.get("llm_em"),
        "n_questions": len(run.get("results", [])),
    }

baseline_rows = {row["id"]: row for row in baseline.get("results", [])}
post_rows = {row["id"]: row for row in post.get("results", [])}
question_ids = sorted(set(baseline_rows) | set(post_rows))

rows = []
for qid in question_ids:
    b = baseline_rows.get(qid, {})
    p = post_rows.get(qid, {})
    rows.append(
        {
            "id": qid,
            "baseline": {
                "predicted": b.get("predicted"),
                "em": b.get("em"),
                "f1": b.get("f1"),
                "llm_em": b.get("llm_em"),
                "error": b.get("error"),
                "submit_completion_mode": b.get("submit_completion_mode"),
            },
            "post_projection": {
                "predicted": p.get("predicted"),
                "em": p.get("em"),
                "f1": p.get("f1"),
                "llm_em": p.get("llm_em"),
                "error": p.get("error"),
                "submit_completion_mode": p.get("submit_completion_mode"),
            },
        }
    )

payload = {
    "baseline_json": str(baseline_path),
    "post_projection_json": str(post_path),
    "baseline_summary": summarize(baseline),
    "post_projection_summary": summarize(post),
    "per_question": rows,
}
out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
print(out_path)
PY
}

main() {
  mkdir -p "${RESULTS_ROOT}"
  touch "${FOLLOWTHROUGH_LOG}"
  trap restore_original_graph EXIT

  log "starting Plan 22 followthrough"
  log "repo=${REPO_ROOT}"
  log "baseline_json=${BASELINE_JSON}"
  resume_build_if_needed

  swap_projection_graph_in
  local post_json
  post_json="$(run_post_projection_benchmark)"
  log "post-projection benchmark json=${post_json}"

  local compare_json
  compare_json="$(write_comparison_json "${REPO_ROOT}/${BASELINE_JSON}" "${post_json}")"
  log "comparison written to ${compare_json}"
  log "Plan 22 followthrough completed"
}

main "$@"
