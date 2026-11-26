"""Download models with automatic resume. Usage: python download.py repo_id [repo_id ...]"""
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

from huggingface_hub import HfApi, snapshot_download  # noqa: E402

for repo in sys.argv[1:]:
    files = HfApi().list_repo_files(repo)
    # Prefer one weight format so we don't download the same weights twice.
    if any(f.endswith(".safetensors") for f in files):
        weights = ["*.safetensors"]
    else:
        weights = ["*.bin"]
    patterns = ["*.json", "*.txt", "*.model", "*.tiktoken", *weights]
    for attempt in range(1, 61):
        try:
            path = snapshot_download(repo, allow_patterns=patterns)
            print(f"Done {repo}: {path}", flush=True)
            break
        except Exception as exc:
            print(f"{repo} attempt {attempt} interrupted ({type(exc).__name__}: {str(exc)[:120]})", flush=True)
            time.sleep(5)
