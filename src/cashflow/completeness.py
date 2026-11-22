"""Check that each account's statements form an unbroken run with no duplicates."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from cashflow.bank_h import Transaction


@dataclass(frozen=True)
class Statement:
    source: str
    sort_code: str
    account_number: str
    account_name: str
    start: date
    end: date
    opening: Decimal | None
    closing: Decimal | None

    @property
    def account(self) -> str:
        return f"{self.sort_code} {self.account_number}"


@dataclass(frozen=True)
class Finding:
    kind: str  # "missing", "duplicate", "conflict", "overlap" or "balance_break"
    account: str
    start: date
    end: date
    sources: tuple[str, ...]
    message: str


def summarise(source: str, transactions: list[Transaction]) -> Statement:
    first, last = transactions[0], transactions[-1]
    return Statement(
        source=source,
        sort_code=first.sort_code,
        account_number=first.account_number,
        account_name=first.account_name,
        start=first.statement_start,
        end=first.statement_end,
        opening=first.balance if first.kind == "opening_balance" else None,
        closing=last.balance if last.kind == "closing_balance" else None,
    )


def check_completeness(statements: list[Statement]) -> list[Finding]:
    """Compare each account's consecutive statements, in date order, for gaps, repeats and balance breaks."""
    findings = []
    by_account = defaultdict(list)
    for statement in statements:
        by_account[statement.account].append(statement)

    for account, run in sorted(by_account.items()):
        # Shortest name first, so "Statement.pdf" is kept over a re-download like "Statement-2.pdf".
        run.sort(key=lambda s: (s.start, s.end, len(s.source), s.source))
        previous = run[0]
        for statement in run[1:]:
            if (statement.start, statement.end) == (previous.start, previous.end):
                same = (statement.opening, statement.closing) == (previous.opening, previous.closing)
                findings.append(
                    Finding(
                        "duplicate" if same else "conflict",
                        account,
                        statement.start,
                        statement.end,
                        (previous.source, statement.source),
                        f"{statement.source} repeats {previous.source}"
                        if same
                        else f"{statement.source} and {previous.source} cover the same period with different balances",
                    )
                )
                continue  # compare the next statement against the first copy
            gap_start, gap_end = previous.end + timedelta(days=1), statement.start - timedelta(days=1)
            if gap_start <= gap_end:
                findings.append(
                    Finding(
                        "missing",
                        account,
                        gap_start,
                        gap_end,
                        (previous.source, statement.source),
                        f"missing statement for {gap_start} to {gap_end} (between {previous.source} and {statement.source})",
                    )
                )
            elif gap_start > statement.start:
                findings.append(
                    Finding(
                        "overlap",
                        account,
                        statement.start,
                        previous.end,
                        (previous.source, statement.source),
                        f"{statement.source} overlaps {previous.source} from {statement.start} to {previous.end}",
                    )
                )
            elif previous.closing != statement.opening:
                findings.append(
                    Finding(
                        "balance_break",
                        account,
                        statement.start,
                        statement.start,
                        (previous.source, statement.source),
                        f"{previous.source} closes at {previous.closing} but {statement.source} opens at {statement.opening}",
                    )
                )
            previous = statement
    return findings


def duplicate_sources(findings: list[Finding]) -> set[str]:
    """Sources that exactly repeat an earlier statement and can be safely skipped."""
    return {f.sources[1] for f in findings if f.kind == "duplicate"}
