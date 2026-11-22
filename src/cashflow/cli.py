import argparse
import dataclasses
import json
import sys
from pathlib import Path

from cashflow.bank_h import check_balances, parse_statement
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


def transactions(args: argparse.Namespace) -> int:
    try:
        files = [f for f in find_files(args.directory) if f.suffix.lower() == ".pdf"]
    except NotADirectoryError:
        print(f"cashflow: not a directory: {args.directory}", file=sys.stderr)
        return 2
    rows, failed = [], 0
    for path in files:
        source = str(path.relative_to(args.directory))
        parsed = parse_statement(pdf_to_text(path))
        for problem in check_balances(parsed):
            failed += 1
            print(f"cashflow: {source}: {problem}", file=sys.stderr)
        rows.extend({"source": source, **dataclasses.asdict(t)} for t in parsed)
    output = json.dumps(rows, default=_json_value, indent=1) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        sys.stdout.write(output)
    return 1 if failed else 0


def _json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return float(value)  # Decimal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cashflow", description="Eat bank statements, excrete pivot tables.")
    commands = parser.add_subparsers(dest="command", required=True)

    scan_parser = commands.add_parser("scan", help="list the statement files in a directory")
    scan_parser.add_argument("directory", type=Path)
    scan_parser.set_defaults(handler=scan)

    text_parser = commands.add_parser("text", help="print the layout-preserved text of a PDF statement")
    text_parser.add_argument("file", type=Path)
    text_parser.set_defaults(handler=text)

    transactions_parser = commands.add_parser(
        "transactions", help="parse every PDF statement in a directory into JSON transactions"
    )
    transactions_parser.add_argument("directory", type=Path)
    transactions_parser.add_argument("-o", "--output", type=Path, help="write JSON here instead of stdout")
    transactions_parser.set_defaults(handler=transactions)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
