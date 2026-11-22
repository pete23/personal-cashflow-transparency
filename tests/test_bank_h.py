from datetime import date
from decimal import Decimal

from cashflow.bank_h import check_balances, money, parse_statement

# Right edges of the amount columns on each page; they differ, as they do in real statements.
PAGE_COLUMNS = [(46, 57, 68), (47, 58, 70)]


def row(text, paid_out="", paid_in="", balance="", page=0):
    """Lay out one table row with amounts right-aligned under their headers."""
    line = text
    for amount, right in zip((paid_out, paid_in, balance), PAGE_COLUMNS[page]):
        if amount:
            line = line.ljust(right - len(amount.removesuffix(" D"))) + amount
    return line


def header(page):
    out, in_, bal = PAGE_COLUMNS[page]
    left = "       Date     Payment type and details".ljust(out - len("£Paid out"))
    return left + "£Paid out" + "£Paid in".rjust(in_ - out) + "£Balance".rjust(bal - in_)


ACCOUNT_DETAILS = [
    "       Account Name                                Sortcode Account Number Sheet Number",
    "       Ms Alice Example and Mr Bob Longname-Example 00-11-22 12345678 {sheet}",
    "       Exampleton",
    "       Your Bank Account details",
]


def statement(opening_row=True):
    lines = [
        "                                       Your Statement",
        "                                                  OpeningBalance       £100.00",
        "                                                  Payments In          £1,000.00",
        "                                                  Payments Out         £1,150.50",
        "                                                  ClosingBalance       £50.50 D",
        "       3 December to 2 January 2026              Bank Identifier Code",
        *(line.format(sheet=101) for line in ACCOUNT_DETAILS),
        header(0),
        "       A",
    ]
    if opening_row:
        lines.append(row("       02 Dec 25   BALANCEBROUGHTFORWARD   .", balance="100.00"))
    lines += [
        row("       03 Dec 25 DD ACME UTILITIES", paid_out="40.00"),
        row("                VIS INT'L 0001"),
        row("                   SOME SHOP"),
        row("                   USD 12.00 @ 1.2000"),
        row("                   Visa Rate", paid_out="10.00", balance="50.00"),
        row("                   BALANCECARRIEDFORWARD", balance="50.00"),
        "       Level 1, Example House",
        "       3 December to 2 January 2026",
        *(line.format(sheet=102) for line in ACCOUNT_DETAILS),
        header(1),
        row("                   BALANCEBROUGHTFORWARD", balance="50.00", page=1),
        row("       01 Jan 26 CR EMPLOYER LTD", page=1),
        row("                   SALARY", paid_in="1,000.00", page=1),
        row("                SO LANDLORD", paid_out="1,100.50", balance="50.50 D", page=1),
        row("                   BALANCECARRIEDFORWARD", balance="50.50 D", page=1),
    ]
    return "\n".join(lines)


def test_money_handles_overdrawn_suffix():
    assert money("1,234.56") == Decimal("1234.56")
    assert money("£50.50 D") == Decimal("-50.50")


def test_parses_transactions_across_pages():
    txs = parse_statement(statement())
    assert [t.kind for t in txs] == ["opening_balance"] + ["transaction"] * 4 + ["closing_balance"]
    opening, utilities, card, salary, rent, closing = txs

    assert (opening.date, opening.balance, opening.amount) == (date(2025, 12, 2), Decimal("100.00"), None)
    assert (utilities.type, utilities.details, utilities.amount) == ("DD", "ACME UTILITIES", Decimal("-40.00"))
    assert card.details == "INT'L 0001"
    assert card.reference == "SOME SHOP USD 12.00 @ 1.2000 Visa Rate"
    assert (card.amount, card.balance) == (Decimal("-10.00"), Decimal("50.00"))
    assert (salary.date, salary.type, salary.reference, salary.amount) == (date(2026, 1, 1), "CR", "SALARY", Decimal("1000.00"))
    assert (rent.date, rent.amount, rent.balance) == (date(2026, 1, 1), Decimal("-1100.50"), Decimal("-50.50"))
    assert (closing.date, closing.balance) == (date(2026, 1, 2), Decimal("-50.50"))


def test_denormalises_account_details_onto_every_row():
    txs = parse_statement(statement())
    assert {(t.account_name, t.sort_code, t.account_number) for t in txs} == {
        ("Ms Alice Example and Mr Bob Longname-Example Exampleton", "00-11-22", "12345678")
    }
    assert [t.sheet_number for t in txs] == ["101", "101", "101", "102", "102", "102"]
    assert {(t.statement_start, t.statement_end) for t in txs} == {(date(2025, 12, 3), date(2026, 1, 2))}


def test_balances_reconcile():
    assert check_balances(parse_statement(statement())) == []


def test_uses_summary_opening_balance_when_no_brought_forward_row():
    opening = parse_statement(statement(opening_row=False))[0]
    assert (opening.kind, opening.date, opening.balance) == ("opening_balance", date(2025, 12, 2), Decimal("100.00"))


def test_check_balances_reports_mismatch():
    txs = parse_statement(statement())
    txs[1].amount = Decimal("-41.00")
    problems = check_balances(txs)
    assert len(problems) == 1 and "running balance 49.00 but statement shows 50.00" in problems[0]
