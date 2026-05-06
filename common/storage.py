import pickle
import json
from pathlib import Path
from typing import Any


def save_pkl(path: Path, data: Any) -> None:
    with open(path, "wb") as f:
        pickle.dump(data, f)
    print(f"총 {len(data)}개의 key 저장 완료 → {path}")


def load_pkl(path: Path) -> Any:
    with open(path, "rb") as f:
        return pickle.load(f)


def save_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
