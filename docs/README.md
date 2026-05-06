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

사내 Jira `sillog_tasks` 이슈의 description을 LLM으로 정형화(`SillogData`) → 정량(룰) + 정성(LLM) + 감독관 검토 → 항목별 파일/Oracle 적재까지 연결되는 **standalone Python 모듈**. (이전 Airflow DAG 버전은 원격에만 보존, 현 로컬은 분리됨.)
