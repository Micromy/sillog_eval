"""_meta.json 포맷 마이그레이션 (legacy → summary 필드 백필).

기존 _meta.json에 summary 필드 추가:
- 기존 파일을 .bak으로 백업
- items/*.json을 읽어 stats 정확히 재계산
- 자연어 total_summary를 파싱하여 supervisor 정보(feedback, issues, status) 복원
"""
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from common.constants import (
    BACKUP_SUFFIX,
    ITEMS_SUBDIR,
    META_FILENAME,
    PassFail,
    RuleType,
    SupervisorStatus,
)


# ── 자연어 total_summary 파싱 ──────────────────────

def parse_total_summary(text: str) -> Dict:
    if not text:
        return {
            "status": SupervisorStatus.UNKNOWN,
            "approved": False,
            "supervisor_failed": False,
            "feedback": "",
            "issues": [],
            "final_score_from_text": None,
            "rounds_used_from_text": None,
            "error_count_from_text": None,
        }

    result = {
        "status": SupervisorStatus.UNKNOWN,
        "approved": False,
        "supervisor_failed": False,
        "feedback": "",
        "issues": [],
        "final_score_from_text": None,
        "rounds_used_from_text": None,
        "error_count_from_text": None,
    }

    status_match = re.search(r"\[감독관 평가:\s*(.+?)\]", text)
    if status_match:
        status_label = status_match.group(1).strip()
        if status_label == "승인":
            result["status"] = SupervisorStatus.APPROVED
            result["approved"] = True
        elif status_label == "미승인":
            result["status"] = SupervisorStatus.NOT_APPROVED
            result["approved"] = False
        elif status_label == "감독관 검토 실패":
            result["status"] = SupervisorStatus.SUPERVISOR_FAILED
            result["supervisor_failed"] = True

    meta_match = re.search(
        r"\[최종 점수:\s*([\d.]+)점\s*/\s*라운드:\s*(\d+)회\s*/\s*에러:\s*(\d+)건\]",
        text,
    )
    if meta_match:
        result["final_score_from_text"] = float(meta_match.group(1))
        result["rounds_used_from_text"] = int(meta_match.group(2))
        result["error_count_from_text"] = int(meta_match.group(3))

    feedback_match = re.search(
        r"\[감독관 피드백\]\s*\n(.+?)(?=\n\[|\Z)",
        text, re.DOTALL,
    )
    if feedback_match:
        feedback = feedback_match.group(1).strip()
        if feedback != "(피드백 없음)":
            result["feedback"] = feedback

    issues_section = re.search(
        r"\[지적 사항\s*\(\d+건\)\]\s*\n(.+?)(?=\n\[|\Z)",
        text, re.DOTALL,
    )
    if issues_section:
        issues_text = issues_section.group(1)
        issue_pattern = re.compile(
            r"\d+\.\s*(.+?)\n\s*-\s*이유:\s*(.+?)\n\s*-\s*제안:\s*(.+?)(?=\n\d+\.|\Z)",
            re.DOTALL,
        )
        for m in issue_pattern.finditer(issues_text):
            result["issues"].append({
                "criterion": m.group(1).strip(),
                "reason": m.group(2).strip(),
                "suggestion": m.group(3).strip(),
            })

    return result


# ── items 디렉토리에서 stats 재계산 ────────────────

def recalc_stats_from_items(items_dir: Path) -> Tuple[Dict, List]:
    quant_results = []
    qual_results = []

    if not items_dir.exists():
        return _empty_stats(), []

    for item_file in sorted(items_dir.glob("*.json")):
        try:
            with open(item_file, encoding="utf-8") as f:
                item = json.load(f)
            rule_type = item.get("rule_type", "")
            if rule_type == RuleType.QUANTITATIVE:
                quant_results.append(item)
            elif rule_type == RuleType.QUALITATIVE:
                qual_results.append(item)
        except Exception as e:
            print(f"    [warn] {item_file.name} 로드 실패: {e}", file=sys.stderr)

    def count(results, status):
        return sum(1 for r in results if r.get("pass_fail") == status)

    def stats_for(results):
        total = len(results)
        p = count(results, PassFail.PASS)
        pa = count(results, PassFail.PARTIAL)
        f = count(results, PassFail.FAIL)
        return {
            "total": total,
            "pass": p,
            "partial": pa,
            "fail": f,
            "pass_rate": round(p / total * 100, 2) if total else 0.0,
        }

    stats = {
        "quantitative": stats_for(quant_results),
        "qualitative": stats_for(qual_results),
    }

    error_items = []
    for r in quant_results + qual_results:
        if r.get("reasoning", "").startswith("[ERROR]"):
            error_items.append({
                "criterion": r.get("criterion_name", "?"),
                "error": r.get("reasoning", ""),
                "attempts": None,
            })

    return stats, error_items


def _empty_stats():
    empty = {"total": 0, "pass": 0, "partial": 0, "fail": 0, "pass_rate": 0.0}
    return {"quantitative": dict(empty), "qualitative": dict(empty)}


# ── 점수 계산 ──────────────────────────────────

def calc_final_score(stats: Dict) -> float:
    q = stats["quantitative"]
    ql = stats["qualitative"]
    total = q["total"] + ql["total"]
    if total == 0:
        return 0.0
    score = (
        q["pass"] * 1.0 + q["partial"] * 0.5
        + ql["pass"] * 1.0 + ql["partial"] * 0.5
    )
    return round(score / total * 100, 2)


# ── summary 빌드 ──────────────────────────────────

def build_summary_from_legacy(meta: Dict, items_dir: Path) -> Dict:
    parsed = parse_total_summary(meta.get("total_summary", ""))
    stats, error_items_from_items = recalc_stats_from_items(items_dir)

    final_score = calc_final_score(stats)
    if final_score == 0.0 and parsed.get("final_score_from_text") is not None:
        final_score = parsed["final_score_from_text"]

    rounds_used = meta.get("final_round")
    if rounds_used is None:
        rounds_used = parsed.get("rounds_used_from_text") or 1

    error_count = parsed.get("error_count_from_text")
    if error_count is None:
        error_count = len(error_items_from_items)

    summary = {
        "final_score": final_score,
        "rounds_used": rounds_used,
        "supervisor": {
            "status": parsed["status"],
            "approved": parsed["approved"],
            "supervisor_failed": parsed["supervisor_failed"],
            "feedback": parsed["feedback"],
            "issues": parsed["issues"],
        },
        "stats": stats,
        "errors": {
            "count": error_count,
            "items": error_items_from_items,
        },
    }

    return summary


# ── 마이그레이션 본체 ──────────────────────────────

def migrate_meta_file(meta_path: Path, dry_run: bool = False) -> bool:
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        print(f"  [error] {meta_path} 로드 실패: {e}", file=sys.stderr)
        return False

    if "summary" in meta:
        return False

    items_dir = meta_path.parent / ITEMS_SUBDIR
    summary = build_summary_from_legacy(meta, items_dir)

    new_meta = {}
    inserted = False
    for k, v in meta.items():
        new_meta[k] = v
        if k == "total_summary" and not inserted:
            new_meta["summary"] = summary
            inserted = True
    if not inserted:
        new_meta["summary"] = summary

    if dry_run:
        print(f"  [dry-run] {meta_path}")
        print(f"           final_score={summary['final_score']}, "
              f"status={summary['supervisor']['status']}, "
              f"issues={len(summary['supervisor']['issues'])}, "
              f"errors={summary['errors']['count']}")
        return True

    backup_path = meta_path.with_suffix(meta_path.suffix + BACKUP_SUFFIX)
    shutil.copy2(meta_path, backup_path)

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(new_meta, f, ensure_ascii=False, indent=2)

    return True


def find_meta_files(storage_dir: Path, model_filter: Optional[str] = None):
    if not storage_dir.exists():
        print(f"[error] storage_dir 존재하지 않음: {storage_dir}", file=sys.stderr)
        return

    if model_filter:
        model_dirs = [storage_dir / model_filter]
    else:
        model_dirs = [d for d in storage_dir.iterdir() if d.is_dir()]

    for model_dir in model_dirs:
        final_dir = model_dir / "final"
        if not final_dir.exists():
            continue
        for key_dir in sorted(final_dir.iterdir()):
            if not key_dir.is_dir():
                continue
            meta_path = key_dir / META_FILENAME
            if meta_path.exists():
                yield meta_path


def migrate_all(storage_dir: Path, model_filter: Optional[str], dry_run: bool) -> None:
    print(f"[migrate_meta] storage_dir={storage_dir} model={model_filter or '(all)'} "
          f"dry_run={dry_run}")

    total = 0
    migrated = 0
    skipped = 0

    for meta_path in find_meta_files(storage_dir, model_filter):
        total += 1
        if migrate_meta_file(meta_path, dry_run=dry_run):
            migrated += 1
            if not dry_run:
                print(f"  ✓ {meta_path}")
        else:
            skipped += 1

    print(f"\n[migrate_meta] 완료: 전체 {total}건, "
          f"{'예정' if dry_run else '마이그레이션'} {migrated}건, "
          f"스킵 {skipped}건 (이미 마이그레이션됨)")
