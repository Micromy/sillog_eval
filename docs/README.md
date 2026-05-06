# sillog_eval 문서

작성 시점 코드베이스의 **현재 상태**를 정리한 문서. 진행 중인 리팩토링 항목은 루트 `REFACTORING.md`를 SOT로 한다.

## 목차

| 문서 | 내용 |
|------|------|
| [01-structure.md](01-structure.md) | 디렉토리 레이아웃과 task 인벤토리 |
| [02-flow.md](02-flow.md) | 실행 / 데이터 흐름 (run_task.py 디스패치 + 파이프라인) |
| [03-data-model.md](03-data-model.md) | Pydantic 모델 + DB 테이블 / 매핑 |
| [04-policies.md](04-policies.md) | 정책 (저장, DB, LLM, 점수, 재평가, 에러) |
| [05-status.md](05-status.md) | 현재 진행 상태와 TODO |

## 한 줄 요약

사내 Jira `sillog_tasks` 이슈의 description을 LLM으로 정형화(`SillogData`) → 정량(룰) + 정성(LLM) + 감독관 검토 → 항목별 파일/Oracle 적재까지 연결되는 **task-dispatch 기반 코드베이스**. 이전 Airflow `run_task.py` 패턴 그대로.

## 실행 방법

repo 루트(`~/Projects/sillog_eval`)에서 `run_task.py`를 디스패처로 사용:

```bash
python run_task.py <dag> <task_id> [extra args...]
```

| dag.task_id | 용도 | 예시 |
|-------------|------|------|
| `parse fetch_jira` | Jira fetch + 캐시 | `python run_task.py parse fetch_jira` |
| `parse parse_description` | LLM 파싱 (재시도 3회) | `python run_task.py parse parse_description` |
| `score score_issues` | 일괄 평가 | `python run_task.py score score_issues` |
| `save upload_parsed` | parsed JSON → DB | `python run_task.py save upload_parsed --dry-run` |
| `save upload_results` | 평가 결과 → DB | `python run_task.py save upload_results <model_name>` |
| `save migrate_meta` | `_meta.json` 백필 | `python run_task.py save migrate_meta <storage_dir> --dry-run` |
| `save reset_results` | 결과 테이블 삭제 | `python run_task.py save reset_results --rule-set-id 22` |

각 task 모듈은 무인자 `def run()`을 export하므로 Airflow BashOperator에서도 동일하게:
```bash
cd /path/to/sillog_eval && python run_task.py <dag> <task_id>
```

환경 변수(JIRA_*, ORACLE_*, DTGPT_*/DS_LLM_*, FILTER_ID, STORAGE_DIR 등)는 `.env` 또는 BashOperator의 `env={}`로 주입.
