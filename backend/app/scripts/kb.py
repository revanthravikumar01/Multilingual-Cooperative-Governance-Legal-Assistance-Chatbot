"""Knowledge-base command-line tool. Run from the backend folder.

  python -m app.scripts.kb list
      Show every document and its status.

  python -m app.scripts.kb add path\\to\\file.pdf --title "..." --authority "..." \\
         --jurisdiction tamil_nadu --type act --language en [--citation-name "..."] [--published 1983]
      Add one PDF (same as uploading on the /docs page).

  python -m app.scripts.kb rebuild
      Recreate the vector database (chroma_db/) from uploads/ + documents.json.
      Use this after cloning the repo, or after changing chunking settings.

  python -m app.scripts.kb search "How do I register a cooperative society?" [--language ta]
      Show the evidence and citations a question would retrieve.
"""

import argparse
import sys
from pathlib import Path

from app.dependencies import get_document_service, get_retrieval_service
from app.errors import ApiError


def main(argv: list[str] | None = None) -> int:
    # Windows consoles may not be UTF-8 by default; Tamil text needs it.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="python -m app.scripts.kb", description="CIVI knowledge base tool")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="list documents")
    commands.add_parser("rebuild", help="rebuild the vector database from the PDFs")

    add = commands.add_parser("add", help="add a PDF")
    add.add_argument("pdf", type=Path)
    add.add_argument("--title", required=True)
    add.add_argument("--authority", required=True)
    add.add_argument("--jurisdiction", required=True, choices=["tamil_nadu", "central"])
    add.add_argument("--type", required=True, choices=["act", "rules", "scheme", "guideline", "circular", "other"])
    add.add_argument("--language", required=True, choices=["en", "ta"])
    add.add_argument("--citation-name")
    add.add_argument("--published")
    add.add_argument("--validity", default="current", choices=["current", "superseded", "unknown"])

    search = commands.add_parser("search", help="test a question")
    search.add_argument("query")
    search.add_argument("--language", default="en", choices=["en", "ta"])

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            documents = get_document_service()
            for r in documents.list():
                print(f"{r['status']:<10} {r.get('chunk_count') or 0:>5} chunks  {r['document_id']}  ({r['title']})")
                for warning in r.get("warnings") or []:
                    print(f"           warning: {warning}")
                if r.get("error"):
                    print(f"           error: {r['error']}")
            print(f"Total chunks in vector database: {documents.store.count()}")

        elif args.command == "rebuild":
            get_document_service().rebuild()

        elif args.command == "add":
            documents = get_document_service()
            record = documents.register_upload(
                args.pdf.read_bytes(),
                args.pdf.name,
                {
                    "title": args.title,
                    "citation_name": args.citation_name,
                    "issuing_authority": args.authority,
                    "jurisdiction": args.jurisdiction,
                    "doc_type": args.type,
                    "language": args.language,
                    "published_on": args.published,
                    "validity": args.validity,
                },
            )
            print(f"Saved as {record['document_id']}. Processing (the first run downloads the embedding model)...")
            result = documents.process(record["document_id"])
            print(f"{result['status']}: {result.get('chunk_count') or 0} chunks")
            for warning in result.get("warnings") or []:
                print(f"warning: {warning}")
            if result.get("error"):
                print(f"error: {result['error']}")

        elif args.command == "search":
            result = get_retrieval_service().search(args.query, language=args.language)
            if result.translated_query:
                print(f"Translated question: {result.translated_query}")
            if result.translation_error:
                print(f"Translation failed, searched the Tamil text only: {result.translation_error}")
            if not result.sufficient:
                print("No relevant evidence found (the chatbot would say it has no verified information).")
            for e in result.evidence:
                print(f"\n{e.citation['label']}   score={e.score} similarity={e.similarity}")
                print("   " + e.text[:400].replace("\n", "\n   "))
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
