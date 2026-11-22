import argparse
import sys
from pathlib import Path

from cashflow.pdf import pdf_to_text
from cashflow.scan import find_files


def scan(args: argparse.Namespace) -> int:
    try:
        files = find_files(args.directory)
    except NotADirectoryError:
        print(f"cashflow: not a directory: {args.directory}", file=sys.stderr)
        return 2
    for path in files:
        print(path.relative_to(args.directory))
    return 0


def text(args: argparse.Namespace) -> int:
    if not args.file.is_file():
        print(f"cashflow: not a file: {args.file}", file=sys.stderr)
        return 2
    print(pdf_to_text(args.file))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cashflow", description="Eat bank statements, excrete pivot tables.")
    commands = parser.add_subparsers(dest="command", required=True)

    scan_parser = commands.add_parser("scan", help="list the statement files in a directory")
    scan_parser.add_argument("directory", type=Path)
    scan_parser.set_defaults(handler=scan)

    text_parser = commands.add_parser("text", help="print the layout-preserved text of a PDF statement")
    text_parser.add_argument("file", type=Path)
    text_parser.set_defaults(handler=text)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
