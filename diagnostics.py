"""Local error reports without credentials, HTTP payloads or exception messages."""
import json
import traceback
import uuid
from datetime import datetime
from pathlib import Path
import settings

def record(stage, exc):
    code = uuid.uuid4().hex[:8]
    report = {"id": code, "time": datetime.now().isoformat(timespec="seconds"),
              "stage": stage, "exception": type(exc).__name__,
              "frames": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                         for f in traceback.extract_tb(exc.__traceback__)]}
    for field in ("winerror", "hresult", "errno"):
        value = getattr(exc, field, None)
        if isinstance(value, int): report[field] = value
    try:
        p = settings.config_path().with_name("errors.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > 256_000:
            p.write_text("", encoding="utf-8")
        with p.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return f"{type(exc).__name__} / {code}"
