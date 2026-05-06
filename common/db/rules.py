# -*- coding: utf-8 -*-
"""`eval_task_rule_item` 테이블 조회 헬퍼.

DB가 평가 항목(rule item)의 SOT. eval_method 컬럼으로 정량(rule)/정성(llm) 구분.
criteria_text가 평가 질문 텍스트.
"""
from typing import Dict, Tuple

from common import db


# ── 활성 rule item 로드 ─────────────────────────────

def load_rule_items(eval_method: str) -> Dict[str, str]:
    """active rule items를 {item_name: criteria_text} dict로 반환.

    Args:
        eval_method: `EvalMethod.RULE` 또는 `EvalMethod.LLM`

    Returns:
        {item_name: criteria_text} (avail='Y'만)
    """
    rows = db.select(
        """
        SELECT item_name, criteria_text
        FROM eval_task_rule_item
        WHERE eval_method = :em
          AND avail = 'Y'
        """,
        em=eval_method,
    )
    return {r["item_name"]: r["criteria_text"] for r in rows}


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
