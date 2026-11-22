"""Parse the layout-preserved text of a bank H statement into transactions.

A statement is a run of pages. Each page repeats the account details and a
transaction table whose header row ("Paid out", "Paid in", "Balance") gives the
right edge of each amount column; amounts are assigned to columns by position.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

AMOUNT = re.compile(r"(?<![\d,.])\d{1,3}(?:,\d{3})*\.\d{2}(?: D)?(?!\d)")
ROW_DATE = re.compile(r"^\s*(\d{2} [A-Z][a-z]{2} \d{2})\s")
PERIOD = re.compile(r"^\s*(\d{1,2} [A-Z][a-z]+(?: \d{4})?) to (\d{1,2} [A-Z][a-z]+ \d{4})(?:\s{2,}|$)")
ACCOUNT = re.compile(r"^\s*(.*?)\s+(\d{2}-\d{2}-\d{2})\s+(\d{8})\s+(\d+)\s*$")
SUMMARY = re.compile(r"(Opening|Closing)\s*Balance\s+£?(\d{1,3}(?:,\d{3})*\.\d{2}(?: D)?)")
HEADER = re.compile(r"Paid\s*out\s+£?\s*Paid\s*in\s+£?\s*Balance")
# Some payers print as "<payment reference><name>" with no space, e.g. "123456789X EXAM P".
GLUED_REFERENCE = re.compile(r"^(\d{6,})(?=[A-Z])")

# Amounts are right-aligned under their headers; text extraction can drift a few characters.
COLUMN_TOLERANCE = 4


@dataclass
class Transaction:
    kind: str  # "transaction", "opening_balance" or "closing_balance"
    date: date
    type: str
    details: str
    reference: str
    amount: Decimal | None
    balance: Decimal | None
    account_name: str
    sort_code: str
    account_number: str
    sheet_number: str
    statement_start: date
    statement_end: date


@dataclass
class _Account:
    name: str = ""
    sort_code: str = ""
    account_number: str = ""
    sheet_number: str = ""


def money(text: str) -> Decimal:
    """Parse '1,234.56' or '1,234.56 D' (overdrawn) into a signed Decimal."""
    text = text.replace("£", "").replace(",", "").strip()
    if text.endswith(" D"):
        return -Decimal(text.removesuffix(" D"))
    return Decimal(text)


def parse_statement(text: str) -> list[Transaction]:
    lines = [line.rstrip() for line in text.splitlines()]
    start, end = _period(lines)
    summary = {kind: money(value) for kind, value in SUMMARY.findall(text.replace("\n", " "))[:2]}

    account = _Account()
    columns: dict[str, int] | None = None
    current_date: date | None = None
    pending: list[str] = []
    carried_forward: Decimal | None = None
    transactions: list[Transaction] = []
    expecting_account = expecting_name_wrap = False

    def emit(kind, details, reference="", type_="", amount=None, balance=None, when=None):
        transactions.append(
            Transaction(
                kind=kind,
                date=when or current_date,
                type=type_,
                details=details,
                reference=reference,
                amount=amount,
                balance=balance,
                account_name=account.name,
                sort_code=account.sort_code,
                account_number=account.account_number,
                sheet_number=account.sheet_number,
                statement_start=start,
                statement_end=end,
            )
        )

    for line in lines:
        if expecting_account:
            match = ACCOUNT.match(line)
            if match:
                name, account.sort_code, account.account_number, account.sheet_number = match.groups()
                if not account.name:
                    account.name = name
                    expecting_name_wrap = True
            expecting_account = False
            continue
        if "Sortcode" in line and "Account Number" in line:
            expecting_account = True
            continue
        if expecting_name_wrap:
            # A long account name wraps onto the line after the account details.
            if line.strip() and not line.strip().startswith("Your ") and not HEADER.search(line):
                account.name = f"{account.name} {line.strip()}"
            expecting_name_wrap = False

        if HEADER.search(line):
            columns = _columns(line)
            continue
        if columns is None:
            continue

        squashed = line.replace(" ", "")
        if "BALANCECARRIEDFORWARD" in squashed:
            carried_forward = _amounts(line, columns).get("balance", carried_forward)
            columns = None  # end of this page's table
            continue

        row_date = ROW_DATE.match(line)
        if row_date:
            current_date = datetime.strptime(row_date.group(1), "%d %b %y").date()
            line = " " * row_date.end() + line[row_date.end() :]  # blank the date, keeping column positions

        amounts = _amounts(line, columns)
        if "BALANCEBROUGHTFORWARD" in squashed:
            if not transactions:  # later pages' brought-forward rows repeat the previous page's total
                emit("opening_balance", "Balance brought forward", balance=amounts.get("balance"))
            continue

        text_part = _strip_amounts(line, columns).strip()
        if text_part in ("A", "."):
            text_part = ""
        if text_part:
            pending.append(text_part)
        if "out" in amounts or "in" in amounts:
            first, *rest = pending or [""]
            type_, _, details = first.partition(" ")
            details = details.strip()
            glued = GLUED_REFERENCE.match(details)
            if glued:
                details = details[glued.end() :]
                rest.insert(0, glued.group(1))
            amount = amounts.get("in", Decimal(0)) - amounts.get("out", Decimal(0))
            emit("transaction", details, " ".join(rest), type_, amount, amounts.get("balance"))
            pending = []

    if not any(t.kind == "opening_balance" for t in transactions):
        # Some statements (e.g. a newly opened account) have no brought-forward row.
        emit("opening_balance", "Opening balance", balance=summary.get("Opening"), when=start - timedelta(days=1))
        transactions.insert(0, transactions.pop())
    # Prefer the table's own figure: the summary box occasionally extracts with a split digit.
    closing = carried_forward if carried_forward is not None else summary.get("Closing")
    emit("closing_balance", "Balance carried forward", balance=closing, when=end)
    return transactions


def check_balances(transactions: list[Transaction]) -> list[str]:
    """Return problems found reconciling amounts against opening, running and closing balances."""
    problems = []
    running = None
    for t in transactions:
        if t.kind == "opening_balance":
            running = t.balance
            if running is None:
                return ["no opening balance found"]
        elif t.kind == "transaction":
            running += t.amount
            if t.balance is not None and t.balance != running:
                problems.append(f"{t.date} {t.details}: running balance {running} but statement shows {t.balance}")
                running = t.balance
        elif t.kind == "closing_balance" and t.balance != running:
            problems.append(f"closing balance {t.balance} but transactions sum to {running}")
    return problems


def _period(lines: list[str]) -> tuple[date, date]:
    for line in lines:
        match = PERIOD.match(line)
        if match:
            end = datetime.strptime(match.group(2), "%d %B %Y").date()
            start_text = match.group(1)
            if re.search(r"\d{4}$", start_text):
                return datetime.strptime(start_text, "%d %B %Y").date(), end
            start = datetime.strptime(f"{start_text} {end.year}", "%d %B %Y").date()
            if start > end:
                start = start.replace(year=end.year - 1)
            return start, end
    raise ValueError("statement period not found")


def _columns(header: str) -> dict[str, int]:
    paid_out = re.search(r"Paid\s*out", header)
    paid_in = re.search(r"Paid\s*in", header)
    balance = re.search(r"Balance", header[paid_in.end() :])
    return {"out": paid_out.end(), "in": paid_in.end(), "balance": paid_in.end() + balance.end()}


def _column_matches(line: str, columns: dict[str, int]):
    for match in AMOUNT.finditer(line):
        right = match.end() - (2 if match.group().endswith(" D") else 0)
        column = min(columns, key=lambda c: abs(columns[c] - right))
        if abs(columns[column] - right) <= COLUMN_TOLERANCE:
            yield column, match


def _amounts(line: str, columns: dict[str, int]) -> dict[str, Decimal]:
    return {column: money(match.group()) for column, match in _column_matches(line, columns)}


def _strip_amounts(line: str, columns: dict[str, int]) -> str:
    for _, match in sorted(_column_matches(line, columns), key=lambda cm: cm[1].start(), reverse=True):
        line = line[: match.start()] + line[match.end() :]
    return re.sub(r"\s+", " ", line)
