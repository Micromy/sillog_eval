# sillog_eval 문서

작성 시점 코드베이스의 **현재 상태**를 정리한 문서. 진행 중인 리팩토링 항목은 루트 `REFACTORING.md`를 SOT로 한다.

## 목차

| 문서 | 내용 |
|------|------|
| [01-structure.md](01-structure.md) | 모듈 구조와 책임 분담 |
| [02-flow.md](02-flow.md) | 실행 / 데이터 흐름 (Jira → 파싱 → 평가 → DB) |
| [03-data-model.md](03-data-model.md) | Pydantic 모델 + DB 테이블 / 매핑 |
| [04-policies.md](04-policies.md) | 정책 (저장, DB, LLM, 점수, 재평가, 에러) |
| [05-status.md](05-status.md) | 현재 진행 상태와 TODO |

## 한 줄 요약

사내 Jira `sillog_tasks` 이슈의 description을 LLM으로 정형화(`SillogData`) → 정량(룰) + 정성(LLM) + 감독관 검토 → 항목별 파일/Oracle 적재까지 연결되는 **standalone Python 패키지**. (이전 Airflow DAG 버전은 원격에만 보존, 현 로컬은 분리됨.)

## 실행 방법

패키지 형태로 import되도록 모든 내부 import는 상대 import. 부모 디렉터리(`~/Projects/`)에서 `python -m sillog_eval.<module>` 식으로 호출.

| 모듈 | 용도 | 예시 |
|------|------|------|
| `sillog_eval.main` | end-to-end (Jira fetch → 파싱 → 평가) | `python -m sillog_eval.main` |
| `sillog_eval.upload_parsed` | 로컬 parsed JSON → DB 적재 | `python -m sillog_eval.upload_parsed --dry-run` |
| `sillog_eval.migrate_eval_results` | 평가 결과 → DB 마이그레이션 | `python -m sillog_eval.migrate_eval_results <model_name>` |
| `sillog_eval.migrate_meta` | `_meta.json` 포맷 백필 | `python -m sillog_eval.migrate_meta <storage_dir> --dry-run` |
| `sillog_eval.reset_eval_results` | 평가 결과 테이블 리셋 | `python -m sillog_eval.reset_eval_results --rule-set-id 22` |

각 모듈은 무인자 `run()` entry를 export하므로 Airflow BashOperator에서 `python -m sillog_eval.<module>` 호출도 동일하게 가능. 환경 변수는 `.env` 또는 BashOperator의 `env={}`로 주입.
