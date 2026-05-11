# 시나리오 2: 중단 후 재개 (수동)

자동화 어려운 부분이라 수동 step-by-step.

## 준비

```bash
source tests/.env   # 또는 export 직접
cd $(dirname $(find ~ -name run_task.py -path '*/sillog_eval/*' | head -1))

RUN_ID="test_resume_$(date +%Y%m%d_%H%M%S)"
RSID="${TEST_EVAL_RULE_SET_ID}"

echo "RUN_ID=$RUN_ID"
echo "RSID=$RSID"
```

## Step 1: fetch_jira (캐시 생성)

```bash
python run_task.py parse fetch_jira
ls "$SCORER_STORAGE_DIR/jira_issues.pkl"   # 존재 확인
```

## Step 2: parse_description 도중 Ctrl+C

```bash
python run_task.py parse parse_description --run-id "$RUN_ID"
# 진행되는 동안 ~3건쯤 처리됐을 때 Ctrl+C
```

## Step 3: DB 상태 확인 (혼재)

```sql
SELECT status, COUNT(*) FROM eval_task_parsed 
WHERE run_id = '$RUN_ID' GROUP BY status;
```
→ `PENDING` 일부 + `DONE` 일부가 보여야 정상 (Ctrl+C 시점에 placeholder만 만들어진 row 존재).

## Step 4: 같은 RUN_ID로 재실행 (재개)

```bash
python run_task.py parse parse_description --run-id "$RUN_ID"
```
→ 콘솔: `[parse_description] 전체 N건 / 완료 M건 / 대상 K건` — 완료 건은 skip되어 K = N - M

끝나면:
```sql
SELECT COUNT(*) FROM eval_task_parsed 
WHERE run_id = '$RUN_ID' AND status = 'PENDING';
```
→ 0이면 정상 (모두 DONE).

## Step 5: score도 같은 패턴으로 검증 (선택)

```bash
python run_task.py score score_issues --run-id "$RUN_ID" --eval-rule-set-id "$RSID"
# Ctrl+C
python run_task.py score score_issues --run-id "$RUN_ID" --eval-rule-set-id "$RSID"
# 완료 확인
```

## Step 6: 정리

```bash
python run_task.py cleanup cleanup_test_db --run-id-prefix "$RUN_ID" --execute --yes
python run_task.py cleanup cleanup_files
```

## 기대 결과

- 중단해도 데이터 손실 없음 (PENDING으로 남음)
- 재실행 시 자동 skip + 누락 처리
- 최종적으로 모두 DONE
