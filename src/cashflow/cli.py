import argparse
import dataclasses
import json
import sys
from pathlib import Path

from cashflow.bank_h import Transaction, check_balances, parse_statement
from cashflow.completeness import Finding, check_completeness, duplicate_sources, summarise
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


def _load_statements(directory: Path) -> tuple[dict[str, list[Transaction]], int]:
    """Parse every PDF under directory, reporting statements that fail to reconcile."""
    statements, failed = {}, 0
    for path in find_files(directory):
        if path.suffix.lower() != ".pdf":
            continue
        source = str(path.relative_to(directory))
        statements[source] = parse_statement(pdf_to_text(path))
        for problem in check_balances(statements[source]):
            failed += 1
            print(f"cashflow: {source}: {problem}", file=sys.stderr)
    return statements, failed


def _completeness(statements: dict[str, list[Transaction]]) -> list[Finding]:
    return check_completeness([summarise(source, txs) for source, txs in statements.items()])


def transactions(args: argparse.Namespace) -> int:
    try:
        statements, failed = _load_statements(args.directory)
    except NotADirectoryError:
        print(f"cashflow: not a directory: {args.directory}", file=sys.stderr)
        return 2
    findings = _completeness(statements)
    skipped = duplicate_sources(findings)
    for finding in findings:
        note = " (skipped)" if finding.kind == "duplicate" else ""
        print(f"cashflow: {finding.account}: {finding.message}{note}", file=sys.stderr)
    rows = [
        {"source": source, **dataclasses.asdict(t)}
        for source, txs in statements.items()
        if source not in skipped
        for t in txs
    ]
    output = json.dumps(rows, default=_json_value, indent=1) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        sys.stdout.write(output)
    return 1 if failed else 0


def check(args: argparse.Namespace) -> int:
    try:
        statements, failed = _load_statements(args.directory)
    except NotADirectoryError:
        print(f"cashflow: not a directory: {args.directory}", file=sys.stderr)
        return 2
    summaries = [summarise(source, txs) for source, txs in statements.items()]
    findings = check_completeness(summaries)
    for account in sorted({s.account for s in summaries}):
        run = [s for s in summaries if s.account == account]
        print(
            f"{account} {run[0].account_name}: {len(run)} statements, "
            f"{min(s.start for s in run)} to {max(s.end for s in run)}"
        )
        for finding in findings:
            if finding.account == account:
                print(f"  {finding.kind}: {finding.message}")
    return 1 if failed or findings else 0


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

    check_parser = commands.add_parser(
        "check", help="report missing, duplicate and overlapping statements for each account"
    )
    check_parser.add_argument("directory", type=Path)
    check_parser.set_defaults(handler=check)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
