# common/db.py

"""Oracle DB 연결 / 쿼리 헬퍼.

DAG의 BashOperator가 Jinja 템플릿으로 다음 env를 주입 필요:
  - ORACLE_USER     : "{{ conn.oracle_default.login }}"
  - ORACLE_PASSWORD : "{{ conn.oracle_default.password }}"
  - ORACLE_DSN      : "{{ conn.oracle_default.host }}"  (tnsname alias)
"""

import contextlib
import os
from typing import Any, Iterator

from dotenv import load_dotenv
import oracledb

try:
    oracledb.init_oracle_client(lib_dir=os.environ.get('ORACLE_PATH'))
except oracledb.ProgrammingError as e:
    # DPY-2017이면 이미 같은/다른 인자로 초기화된 상태
    if "DPY-2017" not in str(e):
        raise


load_dotenv()


# ─── 연결 ──────────────────────────────────────────────────────

def _required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"Required environment variable {key} is not set. "
            f"Check DAG's BashOperator env."
        )
    return val


def get_connection() -> oracledb.Connection:
    """매 호출마다 새 connection 생성. cursor() 컨텍스트에서 자동 close."""
    return oracledb.connect(
        user=_required("ORACLE_USER"),
        password=_required("ORACLE_PASSWORD"),
        dsn=_required("ORACLE_DSN"),
    )


@contextlib.contextmanager
def cursor() -> Iterator[oracledb.Cursor]:
    """with cursor() as cur: 패턴.
    
    정상 종료 시 commit, 예외 시 rollback. 항상 connection close.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── 쿼리 헬퍼 ──────────────────────────────────────────────────
def _rows_to_dicts(cur: oracledb.Cursor) -> list[dict[str, Any]]:
    cols = [c[0].lower() for c in cur.description]
    rows = []
    for raw in cur.fetchall():
        row = {}
        for col, val in zip(cols, raw):
            # CLOB은 .read()로 문자열화
            if hasattr(val, "read"):
                val = val.read()
            row[col] = val
        rows.append(row)
    return rows


def select(sql: str, **params) -> list[dict[str, Any]]:
    """SELECT 결과를 dict 리스트로 반환."""
    with cursor() as cur:
        cur.execute(sql, params)
        return _rows_to_dicts(cur)


def fetch(sql: str, **params) -> dict[str, Any] | None:
    """첫 한 건만. 없으면 None."""
    rows = select(sql, **params)
    return rows[0] if rows else None


def execute(sql: str, **params) -> None:
    """단일 INSERT/UPDATE/DELETE."""
    with cursor() as cur:
        cur.execute(sql, params)


def execute_many(sql: str, rows: list[dict[str, Any]]) -> None:
    """배치 INSERT/UPDATE. rows가 비면 no-op."""
    if not rows:
        return
    with cursor() as cur:
        cur.executemany(sql, rows)
