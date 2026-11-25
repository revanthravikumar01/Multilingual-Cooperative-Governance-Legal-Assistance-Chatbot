"""Measure retrieval quality on the test questions in evaluation/questions.json.

  python -m app.scripts.evaluate                          # use the thresholds from .env
  python -m app.scripts.evaluate --threshold 0.4          # try a different relevance threshold
  python -m app.scripts.evaluate --sweep 0.35,0.4,0.45    # compare several thresholds (summary only)
  python -m app.scripts.evaluate --verbose                # also show everything found per question

For each in-scope question it checks whether an acceptable section is the top result
(hit@1) or anywhere in the returned evidence (hit@k). For each out-of-scope question
it checks that nothing was returned (so the chatbot would say it has no verified information).
"""

import argparse
import json
import sys
from dataclasses import dataclass

from app.config import BACKEND_DIR
from app.dependencies import get_retrieval_service
from app.utils.legal_chunker import section_key

QUESTIONS_FILE = BACKEND_DIR / "evaluation" / "questions.json"


@dataclass
class Score:
    in_scope: int = 0
    hit1: int = 0
    hitk: int = 0
    out_scope: int = 0
    rejected: int = 0

    def summary(self) -> str:
        return (
            f"in scope: top correct {self.hit1}/{self.in_scope}, anywhere {self.hitk}/{self.in_scope} | "
            f"out of scope rejected {self.rejected}/{self.out_scope}"
        )


def _matches(evidence, expect: list[dict]) -> bool:
    doc_id = evidence.metadata.get("document_id", "")
    key = evidence.metadata.get("section_key")
    return any(doc_id.startswith(e["doc"]) and key in {section_key(s) for s in e["sections"]} for e in expect)


def run(retrieval, questions: list[dict], show: bool, verbose: bool) -> Score:
    score = Score()
    for q in questions:
        result = retrieval.search(q["query"], language=q["language"], jurisdiction=q.get("jurisdiction"))
        top = result.evidence[0] if result.evidence else None
        if q["expect"]:
            score.in_scope += 1
            first = bool(top and _matches(top, q["expect"]))
            anywhere = any(_matches(e, q["expect"]) for e in result.evidence)
            score.hit1 += first
            score.hitk += anywhere
            mark = "OK  " if first else ("near" if anywhere else "MISS")
        else:
            score.out_scope += 1
            score.rejected += not result.sufficient
            mark = "OK  " if not result.sufficient else "LEAK"
        if not show:
            continue
        found = f"{top.citation['label']} (sim {top.similarity})" if top else "nothing found"
        print(f"[{mark}] {q['id']:<28} -> {found}")
        if result.translated_query:
            print(f"       translated: {result.translated_query}")
        if verbose:
            for e in result.evidence[1:]:
                print(f"       also: {e.citation['label']} (sim {e.similarity}, score {e.score})")
    return score


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m app.scripts.evaluate")
    parser.add_argument("--threshold", type=float, help="override CIVI_RELEVANCE_THRESHOLD")
    parser.add_argument("--tamil-threshold", type=float, help="override CIVI_TAMIL_QUERY_THRESHOLD")
    parser.add_argument("--sweep", help="comma-separated thresholds to compare, e.g. 0.35,0.4,0.45")
    parser.add_argument("--language", choices=["en", "ta"], help="only questions in this language")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    retrieval = get_retrieval_service()
    if args.threshold is not None:
        retrieval.relevance_threshold = args.threshold
    if args.tamil_threshold is not None:
        retrieval.tamil_query_threshold = args.tamil_threshold
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    if args.language:
        questions = [q for q in questions if q["language"] == args.language]

    if args.sweep:
        print(f"Tamil-text threshold: {retrieval.tamil_query_threshold}")
        for value in [float(v) for v in args.sweep.split(",")]:
            retrieval.relevance_threshold = value
            if args.tamil_threshold is None:
                retrieval.tamil_query_threshold = value
            print(f"threshold {value:.2f}: {run(retrieval, questions, show=False, verbose=False).summary()}")
        return 0

    print(f"Relevance threshold: {retrieval.relevance_threshold}, Tamil-text threshold: {retrieval.tamil_query_threshold}\n")
    score = run(retrieval, questions, show=True, verbose=args.verbose)
    print(f"\n{score.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
