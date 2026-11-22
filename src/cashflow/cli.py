import argparse
import dataclasses
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from cashflow.bank_h import Transaction, check_balances, parse_statement
from cashflow.completeness import Finding, check_completeness, duplicate_sources, summarise
from cashflow.pdf import pdf_to_text
from cashflow.review import review, summary
from cashflow.rules import apply, load_rules, load_taxonomy
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
    _assign_ids(rows)
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


def classify(args: argparse.Namespace) -> int:
    rows = json.loads(args.transactions.read_text())
    taxonomy = load_taxonomy(args.taxonomy)

    def reclassify():
        apply(rows, load_rules(args.rules, taxonomy))
        args.transactions.write_text(json.dumps(rows, indent=1) + "\n")

    try:
        reclassify()
    except ValueError as e:
        print(f"cashflow: {e}", file=sys.stderr)
        return 2
    if args.no_review or not sys.stdin.isatty():
        print(summary(rows))
        return 0

    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import FuzzyCompleter, WordCompleter

    categories = PromptSession(
        completer=FuzzyCompleter(WordCompleter(taxonomy, sentence=True, ignore_case=True)),
        complete_while_typing=True,
    )
    plain = PromptSession()
    try:
        review(rows, args.rules, taxonomy, categories.prompt, plain.prompt, reclassify)
    except (EOFError, KeyboardInterrupt):
        print()
    print(summary(rows))
    return 0


def _assign_ids(rows: list[dict]) -> None:
    """Give each row a short id that is stable across reruns, so manual classifications stick.

    Built from the row's content rather than its source file name; identical rows on
    the same day are told apart by their order.
    """
    seen = Counter()
    for row in rows:
        key = "|".join(
            str(row[k]) for k in ("account_number", "kind", "date", "type", "details", "reference", "amount", "balance")
        )
        seen[key] += 1
        row["id"] = hashlib.sha1(f"{key}|{seen[key]}".encode()).hexdigest()[:12]


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

    classify_parser = commands.add_parser(
        "classify", help="apply rules to a transactions JSON file, then review the biggest unclassified rows"
    )
    classify_parser.add_argument("transactions", type=Path, help="JSON from `cashflow transactions`, updated in place")
    classify_parser.add_argument("--rules", type=Path, default=Path("rules.toml"), help="personal rules file (default: rules.toml)")
    classify_parser.add_argument("--taxonomy", type=Path, help="taxonomy TOML (default: the built-in one)")
    classify_parser.add_argument("--no-review", action="store_true", help="apply rules and report, without prompting")
    classify_parser.set_defaults(handler=classify)

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
