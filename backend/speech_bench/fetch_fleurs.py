"""Fetch a few FLEURS clips per language without downloading the whole parquet file.

Reads only the parquet footer and the first row group over HTTP range requests.
Usage: python fetch_fleurs.py <out_dir> [count]
"""
import io
import json
import sys
from pathlib import Path

import httpx
import pyarrow.parquet as pq

URL = "https://huggingface.co/datasets/google/fleurs/resolve/refs%2Fconvert%2Fparquet/{cfg}/validation/0000.parquet"


class HttpFile(io.RawIOBase):
    def __init__(self, url):
        self.client = httpx.Client(follow_redirects=True, timeout=60)
        self.url = url
        head = self.client.head(url)
        head.raise_for_status()
        self.size = int(head.headers["content-length"])
        self.url = str(head.url)
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        for attempt in range(10):
            try:
                r = self.client.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
                r.raise_for_status()
                break
            except httpx.HTTPError as exc:
                print(f"  retry {attempt + 1}: {type(exc).__name__}", flush=True)
        data = r.content
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def main():
    out = Path(sys.argv[1])
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    refs = {}
    for cfg, lang in (("ta_in", "ta"), ("en_us", "en")):
        print(f"Reading {cfg}...", flush=True)
        pf = pq.ParquetFile(HttpFile(URL.format(cfg=cfg)))
        print(f"  {pf.metadata.num_row_groups} row groups, {pf.metadata.num_rows} rows", flush=True)
        table = pf.read_row_group(0, columns=["id", "audio", "transcription", "raw_transcription"])
        rows = table.to_pylist()
        seen = set()
        saved = 0
        (out / lang).mkdir(parents=True, exist_ok=True)
        for row in rows:
            if row["id"] in seen:  # FLEURS repeats sentences with different speakers
                continue
            seen.add(row["id"])
            name = f"{lang}_{row['id']}.wav"
            (out / lang / name).write_bytes(row["audio"]["bytes"])
            refs[f"{lang}/{name}"] = {"lang": lang, "text": row["raw_transcription"], "norm": row["transcription"]}
            saved += 1
            if saved >= count:
                break
        print(f"  saved {saved} clips", flush=True)
    (out / "references.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
