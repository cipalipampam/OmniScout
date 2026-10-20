import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.pipeline.end_to_end_pipeline import EndToEndPipeline


def main() -> int:
    raw_text = "  PENGUMUMAN!! Lihat https://x.com/example/1 @akun #Info  "
    frame = pd.DataFrame(
        [{"platform": "X", "source": "https://x.com/example/1", "user_id": "akun", "content": raw_text}]
    )
    pipeline = EndToEndPipeline()
    result = pipeline.execute_preprocessing(frame)

    failures = []
    if result.loc[0, "content"] != raw_text.strip():
        failures.append("whitespace was not normalized")
    if "clean_text" in result.columns:
        failures.append("clean_text should not be generated")
    if failures:
        print("FAILED:", "; ".join(failures))
        return 1
    print("PASSED: mandatory preprocessing preserves content semantics and removes extra whitespace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
