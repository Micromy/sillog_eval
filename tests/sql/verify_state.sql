-- 테스트 후 DB 상태 검증용 SQL 모음.
-- run_id LIKE 'test_%'로 격리되어 있어 운영 데이터 안전.

-- ── 1. 처리 상태 분포 ─────────────────────────────

-- parsed status 분포 (run_id별)
SELECT run_id, status, COUNT(*) cnt
FROM eval_task_parsed
WHERE run_id LIKE 'test_%'
GROUP BY run_id, status
ORDER BY run_id, status;

-- result status 분포 (test parsed에 연결된 것)
SELECT r.eval_rule_set_id, r.status, COUNT(*) cnt
FROM eval_task_result r
WHERE r.task_id IN (
    SELECT task_id FROM eval_task_parsed
    WHERE run_id LIKE 'test_%' AND task_id IS NOT NULL
)
GROUP BY r.eval_rule_set_id, r.status
ORDER BY r.eval_rule_set_id, r.status;


-- ── 2. 실패 사유 모음 ──────────────────────────────

SELECT source_issue_key, status, SUBSTR(failed_reason, 1, 200) reason_prefix
FROM eval_task_parsed
WHERE run_id LIKE 'test_%' AND status = 'FAILED'
ORDER BY parsed_at DESC;

SELECT r.task_id, r.status, SUBSTR(r.failed_reason, 1, 200) reason_prefix
FROM eval_task_result r
WHERE r.task_id IN (
    SELECT task_id FROM eval_task_parsed
    WHERE run_id LIKE 'test_%' AND task_id IS NOT NULL
)
  AND r.status = 'FAILED'
ORDER BY r.evaluated_at DESC;


-- ── 3. 자식 row 정합성 ────────────────────────────

-- DONE인데 자식 0개인 parsed row (잠재 버그)
SELECT p.parsed_id, p.source_issue_key
FROM eval_task_parsed p
WHERE p.run_id LIKE 'test_%' AND p.status = 'DONE'
  AND NOT EXISTS (SELECT 1 FROM eval_task_parsed_check c WHERE c.parsed_id = p.parsed_id)
ORDER BY p.parsed_id;

-- DONE인데 items 0개인 result row
SELECT r.task_eval_id, r.task_id
FROM eval_task_result r
WHERE r.status = 'DONE'
  AND r.task_id IN (SELECT task_id FROM eval_task_parsed WHERE run_id LIKE 'test_%' AND task_id IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM eval_task_result_item i WHERE i.task_eval_id = r.task_eval_id)
ORDER BY r.task_eval_id;


-- ── 4. target_fields 컬럼 점검 ────────────────────

-- 현재 target_fields 설정 (정성 항목만)
SELECT item_name, eval_method, target_fields
FROM eval_task_rule_item
WHERE avail = 'Y' AND eval_method = 'llm'
ORDER BY item_name;

-- 알 수 없는 필드명이 들어간 row 검사
SELECT item_name, target_fields
FROM eval_task_rule_item
WHERE avail = 'Y' AND target_fields IS NOT NULL
  AND REGEXP_REPLACE(
        target_fields,
        '(^|,)\s*(purpose|input_data|task|output|checklist)\s*(,|$)',
        ',', 1, 0
      ) NOT IN ('', ',', ',,');


-- ── 5. 테스트 데이터 카운트 (cleanup 전 확인용) ─────

SELECT
    (SELECT COUNT(*) FROM eval_task_parsed WHERE run_id LIKE 'test_%') AS parsed_test_count,
    (SELECT COUNT(*) FROM eval_task_result r
     WHERE r.task_id IN (SELECT task_id FROM eval_task_parsed WHERE run_id LIKE 'test_%' AND task_id IS NOT NULL)
    ) AS result_test_count
FROM dual;
