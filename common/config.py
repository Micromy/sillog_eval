# -*- coding: utf-8 -*-
"""
전역 설정 - 민감정보는 .env에서 로드.

이 파일은 템플릿입니다. 실제 값은 로컬에서 관리하세요.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# ── 플랫폼 ──────────────────────────────────────────
PLATFORM = os.environ.get("PLATFORM", "DTGPT")  # DTGPT | DS_LLM

# ── DTGPT ───────────────────────────────────────────
DTGPT_URL = os.environ.get("DTGPT_URL", "")
DTGPT_MODEL = os.environ.get("DTGPT_MODEL", "")
DTGPT_TOKEN = os.environ.get("DTGPT_TOKEN", "")

# ── DS_LLM ──────────────────────────────────────────
DS_LLM_URL = os.environ.get("DS_LLM_URL", "")
DS_LLM_MODEL = os.environ.get("DS_LLM_MODEL", "")
DS_LLM_HEADER = {}  # 실제 헤더는 로컬에서 설정

# ── Jira ────────────────────────────────────────────
FILTER_ID = os.environ.get("FILTER_ID", "")
JIRA_VERIFY_SSL = os.environ.get("JIRA_VERIFY_SSL", "false").lower() in ("1", "true", "yes")

# ── 운영 ────────────────────────────────────────────
MIGRATION_USER = os.environ.get("MIGRATION_USER", "migration")

# ── 셧다운 임계값 ───────────────────────────────────
# 한 issue가 retry 3회 후에도 실패한 게 누적 N건이면 task 자체 종료.
# (LLM 서버 다운으로 추정, 무의미한 호출 누적 방지)
SHUTDOWN_THRESHOLD = int(os.environ.get("SHUTDOWN_THRESHOLD", "10"))

# ── LLM 풀 ─────────────────────────────────────────
LLM_POOL_SIZE = int(os.environ.get("LLM_POOL_SIZE", "5"))

# ── 저장 경로 ───────────────────────────────────────
STORAGE_DIR = Path(os.environ.get(
    "SCORER_STORAGE_DIR",
    r"C:\Users\sh0913.park\Documents\evaluation_result\SilLog-Vanguard",
))

# ── 타임아웃/동시성 ──────────────────────────────────
LLM_TIMEOUT = int(os.environ.get("SCORER_LLM_TIMEOUT", "120"))
QUAL_BATCH_FUTURE_TIMEOUT = int(os.environ.get("SCORER_QUAL_BATCH_FUTURE_TIMEOUT", "300"))
ISSUE_TIMEOUT = int(os.environ.get("SCORER_ISSUE_TIMEOUT", "600"))

DEFAULT_MAX_ROUNDS = int(os.environ.get("SCORER_MAX_ROUNDS", "3"))
DEFAULT_MAX_RETRIES = int(os.environ.get("SCORER_MAX_RETRIES", "3"))
DEFAULT_RETRY_DELAY = float(os.environ.get("SCORER_RETRY_DELAY", "2.0"))
DEFAULT_MAX_WORKERS = int(os.environ.get("SCORER_MAX_WORKERS", "3"))
DEFAULT_MAX_QUAL_WORKERS = int(os.environ.get("SCORER_MAX_QUAL_WORKERS", "5"))

# ── 프롬프트 ────────────────────────────────────────
EVALUATE_PROMPT = """..."""  # 실제 프롬프트는 로컬에서 관리
REFINE_PROMPT = """..."""
REVIEW_PROMPT = """..."""
PARSING_TEMPLATE = None  # ChatPromptTemplate 인스턴스 — 로컬에서 설정
