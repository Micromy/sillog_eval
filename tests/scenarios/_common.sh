#!/usr/bin/env bash
# 모든 시나리오에서 공유하는 환경 검증 + 유틸.
# source 해서 사용.

set -euo pipefail

# 필수 env 검증
REQUIRED_VARS=(
    PLATFORM
    JIRA_URL JIRA_USERNAME JIRA_PASSWORD
    ORACLE_USER ORACLE_PASSWORD ORACLE_DSN
    SCORER_STORAGE_DIR
    TEST_EVAL_RULE_SET_ID
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "[ERROR] 필수 env 변수 누락: $var" >&2
        echo "        tests/.env.example 참고" >&2
        exit 1
    fi
done

# FILTER_ID 또는 TEST_JQL 중 하나는 있어야 함
if [ -z "${FILTER_ID:-}" ] && [ -z "${TEST_JQL:-}" ]; then
    echo "[ERROR] FILTER_ID 또는 TEST_JQL 둘 중 하나는 설정 필요" >&2
    exit 1
fi

# run_id는 항상 test_ prefix (cleanup 안전)
TEST_RUN_ID="test_$(date +%Y%m%d_%H%M%S)_$$"
export TEST_RUN_ID

cd "$(dirname "$0")/../.."   # repo 루트로 이동

run_task() {
    python run_task.py "$@"
}

# TEST_JQL이 있으면 --jql 사용, 없으면 FILTER_ID로 fallback
run_fetch_jira() {
    if [ -n "${TEST_JQL:-}" ]; then
        run_task parse fetch_jira --jql "${TEST_JQL}"
    else
        run_task parse fetch_jira
    fi
}

verify_status() {
    local label="$1"
    echo ""
    echo "=== ${label} ==="
    python - <<EOF
import os
from common import db
prefix = os.environ["TEST_RUN_ID"]
rsid = int(os.environ["TEST_EVAL_RULE_SET_ID"])

print(f"-- eval_task_parsed (run_id={prefix})")
rows = db.select(
    "SELECT status, COUNT(*) cnt FROM eval_task_parsed "
    "WHERE run_id = :rid GROUP BY status ORDER BY status",
    rid=prefix,
)
for r in rows:
    print(f"  {r['status']:>10}: {r['cnt']}")

print(f"-- eval_task_result (rule_set_id={rsid}, task_id linked to run)")
rows = db.select(
    "SELECT r.status, COUNT(*) cnt "
    "FROM eval_task_result r "
    "WHERE r.task_id IN (SELECT task_id FROM eval_task_parsed WHERE run_id = :rid AND task_id IS NOT NULL) "
    "  AND r.eval_rule_set_id = :rsid "
    "GROUP BY r.status ORDER BY r.status",
    rid=prefix, rsid=rsid,
)
for r in rows:
    print(f"  {r['status']:>10}: {r['cnt']}")
EOF
}

cleanup_test_data() {
    echo ""
    echo "=== Cleanup ==="
    run_task cleanup cleanup_test_db --run-id-prefix "${TEST_RUN_ID}" --execute --yes
    run_task cleanup cleanup_files --dry-run
}

trap 'echo ""; echo "[INTERRUPT] Ctrl+C 감지. 테스트 데이터 정리:"; cleanup_test_data; exit 130' INT TERM
