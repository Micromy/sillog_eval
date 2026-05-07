# -*- coding: utf-8 -*-
"""`eval_task_rule_item` 테이블 조회 헬퍼.

DB가 평가 항목(rule item)의 SOT. eval_method 컬럼으로 정량(rule)/정성(llm) 구분.
criteria_text가 평가 질문 텍스트. target_fields 컬럼으로 LLM 평가에 들어가는
필드 제한 (NULL/empty = 전체).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from common import db


@dataclass
class RuleItem:
    """eval_task_rule_item 한 행."""
    item_name: str
    criteria_text: str
    target_fields: List[str] = field(default_factory=list)
    """LLM 평가에 포함할 평탄화 필드 (extracted_data 키). 빈 list면 5개 모두."""


# ── 활성 rule item 로드 ─────────────────────────────

def load_rule_items(eval_method: str) -> Dict[str, RuleItem]:
    """active rule items를 {item_name: RuleItem} dict로 반환.

    Args:
        eval_method: `EvalMethod.RULE` 또는 `EvalMethod.LLM`

    Returns:
        {item_name: RuleItem} (avail='Y'만)
    """
    rows = db.select(
        """
        SELECT item_name, criteria_text, target_fields
        FROM eval_task_rule_item
        WHERE eval_method = :em
          AND avail = 'Y'
        """,
        em=eval_method,
    )
    return {
        r["item_name"]: RuleItem(
            item_name=r["item_name"],
            criteria_text=r["criteria_text"],
            target_fields=_parse_target_fields(r.get("target_fields")),
        )
        for r in rows
    }


def _parse_target_fields(raw: Optional[str]) -> List[str]:
    """target_fields 문자열을 list로 파싱.

    NULL/empty → []. 'a,b' → ['a', 'b']. 화이트리스트 검증은 호출처(scorer)에서.
    """
    if not raw:
        return []
    return [f.strip() for f in raw.split(",") if f.strip()]


def load_rule_item_id_map() -> Tuple[Dict[str, int], int]:
    """item_name → eval_rule_item_id 매핑 + latest rule_set_id.

    `save upload_results` task의 결과 적재 시 사용.

    Returns:
        ({item_name: eval_rule_item_id}, latest_eval_rule_set_id)

    Raises:
        RuntimeError: 활성 rule_item이 하나도 없으면.
    """
    rows = db.select(
        """
        SELECT eval_rule_item_id, eval_rule_set_id, item_name
        FROM eval_task_rule_item
        WHERE avail = 'Y'
        """,
    )
    if not rows:
        raise RuntimeError("활성 rule_item이 없음")

    mapping = {row["item_name"]: row["eval_rule_item_id"] for row in rows}
    latest_rule_set_id = max(row["eval_rule_set_id"] for row in rows)

    return mapping, latest_rule_set_id
