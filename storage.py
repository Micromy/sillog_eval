import pickle
import json


def save_pkl(path, data):
    with open(path, "wb") as f:
        pickle.dump(data, f)
    print(f"총 {len(data)}개의 key 저장 완료 → {path}")


def load_pkl(path):
    output = ""
    with open(path, "rb") as f:
        output = pickle.load(f)
    return output


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
