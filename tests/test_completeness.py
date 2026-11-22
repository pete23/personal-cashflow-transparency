from datetime import date
from decimal import Decimal

from cashflow.completeness import Statement, check_completeness, duplicate_sources


def statement(source, start, end, opening, closing, account_number="12345678"):
    return Statement(
        source=source,
        sort_code="00-11-22",
        account_number=account_number,
        account_name="Ms A Example",
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        opening=Decimal(opening),
        closing=Decimal(closing),
    )


JAN = statement("jan.pdf", "2026-01-03", "2026-02-02", "0", "10")
FEB = statement("feb.pdf", "2026-02-03", "2026-03-02", "10", "20")
MAR = statement("mar.pdf", "2026-03-03", "2026-04-02", "20", "30")


def kinds(findings):
    return [(f.kind, f.start, f.end, f.sources) for f in findings]


def test_unbroken_run_has_no_findings():
    assert check_completeness([MAR, JAN, FEB]) == []


def test_reports_missing_period_between_statements():
    assert kinds(check_completeness([JAN, MAR])) == [
        ("missing", date(2026, 2, 3), date(2026, 3, 2), ("jan.pdf", "mar.pdf"))
    ]


def test_accounts_are_checked_separately():
    other = statement("savings.pdf", "2025-06-01", "2025-12-31", "5", "5", account_number="87654321")
    assert check_completeness([JAN, FEB, other]) == []


def test_exact_repeat_is_a_duplicate_and_keeps_the_plain_name():
    copy = statement("feb-2.pdf", "2026-02-03", "2026-03-02", "10", "20")
    findings = check_completeness([JAN, copy, FEB, MAR])
    assert kinds(findings) == [("duplicate", date(2026, 2, 3), date(2026, 3, 2), ("feb.pdf", "feb-2.pdf"))]
    assert duplicate_sources(findings) == {"feb-2.pdf"}


def test_same_period_with_different_balances_is_a_conflict_not_skipped():
    other = statement("feb-2.pdf", "2026-02-03", "2026-03-02", "10", "25")
    findings = check_completeness([JAN, FEB, other])
    assert [f.kind for f in findings] == ["conflict"]
    assert duplicate_sources(findings) == set()


def test_reports_overlap():
    late_feb = statement("feb.pdf", "2026-02-01", "2026-03-02", "10", "20")
    assert kinds(check_completeness([JAN, late_feb])) == [
        ("overlap", date(2026, 2, 1), date(2026, 2, 2), ("jan.pdf", "feb.pdf"))
    ]


def test_reports_balance_that_does_not_carry_over():
    feb = statement("feb.pdf", "2026-02-03", "2026-03-02", "11", "20")
    assert [f.kind for f in check_completeness([JAN, feb])] == ["balance_break"]
