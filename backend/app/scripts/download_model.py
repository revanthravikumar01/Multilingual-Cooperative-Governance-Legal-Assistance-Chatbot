"""Download the embedding model once, resuming automatically if the connection stalls.

  python -m app.scripts.download_model

The model (BAAI/bge-m3, ~2.3 GB) is saved in your user folder (~/.cache/huggingface) and
shared by every project on this computer. Run this once after cloning the repo, then
`python -m app.scripts.kb rebuild`. If your internet drops, just run it again: it continues
from where it stopped.
"""

import os
import sys
import time

# Plain HTTP downloads resume from the partial file; a stall longer than 30 s triggers a retry.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

from huggingface_hub import snapshot_download  # noqa: E402

from app.config import settings  # noqa: E402

MAX_ATTEMPTS = 60


def main() -> int:
    model = settings.embedding_model
    print(f"Downloading {model} (resumes automatically if the connection stalls)...", flush=True)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            path = snapshot_download(model, allow_patterns=["*.json", "*.model", "*.txt", "*.bin", "1_Pooling/*"])
            print(f"Done: {path}")
            return 0
        except KeyboardInterrupt:
            print("\nStopped. Run the command again to continue from where it stopped.")
            return 1
        except Exception as exc:
            print(f"Attempt {attempt} interrupted ({type(exc).__name__}); continuing in 5 s...", flush=True)
            time.sleep(5)
    print("Gave up after many attempts. Check the internet connection and run the command again.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
