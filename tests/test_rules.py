from pathlib import Path

import pytest

import cashflow
from cashflow.review import review, suggested_pattern, unclassified
from cashflow.rules import Rule, Rules, append_manual, append_rule, apply, load_rules, load_taxonomy

# The packaged default, never a personal taxonomy.toml in the working directory.
TAXONOMY = load_taxonomy(Path(cashflow.__file__).parent / "default_taxonomy.toml")


def tx(details, amount, id_=None, type_="VIS", reference="", account="12345678", kind="transaction"):
    return {
        "id": id_ or details,
        "kind": kind,
        "date": "2026-01-01",
        "type": type_,
        "details": details,
        "reference": reference,
        "amount": amount,
        "account_number": account,
    }


def test_taxonomy_is_two_level():
    assert "Transport / Public transport" in TAXONOMY
    assert "Balance / Opening" in TAXONOMY


def test_first_matching_rule_wins_and_manual_beats_rules(tmp_path):
    path = tmp_path / "rules.toml"
    path.write_text(
        """
[[rule]]
category = 'Eating out / Takeaway'
details = 'UBER\\W*EATS'

[[rule]]
category = 'Transport / Taxis'
details = '^uber'

[[manual]]
id = 'special'
category = 'Shopping / Gifts given'
"""
    )
    rows = [tx("UBER * EATS PEND", -20), tx("UBER *TRIP", -12), tx("UBER *TRIP", -99, id_="special"), tx("TESCO", -5)]
    apply(rows, load_rules(path, TAXONOMY))
    assert [(r["group"], r["subcategory"]) for r in rows] == [
        ("Eating out", "Takeaway"),
        ("Transport", "Taxis"),
        ("Shopping", "Gifts given"),
        ("Uncategorised", ""),
    ]
    assert rows[2]["rule"] == "manual"


def test_balance_rows_classify_themselves():
    rows = [tx("Balance brought forward", None, kind="opening_balance")]
    apply(rows, Rules())
    assert (rows[0]["group"], rows[0]["subcategory"]) == ("Balance", "Opening")


def test_rule_fields_and_direction():
    salary = Rule("Income / Salary", {"details": "^ACME", "account": "5678$"}, direction="in")
    assert salary.matches(tx("ACME LTD", 100))
    assert not salary.matches(tx("ACME LTD", -100))
    assert not salary.matches(tx("ACME LTD", 100, account="99999999"))
    assert Rule("Financial / Cash", {"type": "^ATM$"}).matches(tx("CASH", -50, type_="ATM"))


def test_unknown_category_is_rejected(tmp_path):
    path = tmp_path / "rules.toml"
    path.write_text("[[rule]]\ncategory = 'Nope / Nothing'\ndetails = 'X'\n")
    with pytest.raises(ValueError, match="unknown category"):
        load_rules(path, TAXONOMY)


def test_appended_rules_round_trip_including_quotes_and_backslashes(tmp_path):
    path = tmp_path / "rules.toml"
    append_rule(path, Rule("Shopping / Online", {"details": r"^AMZ\*", "reference": "Bob's"}, direction="out"))
    append_manual(path, "abc123", "Leisure / Hobbies")
    rules = load_rules(path, TAXONOMY)
    assert rules.rules[0].patterns == {"details": r"^AMZ\*", "reference": "Bob's"}
    assert rules.rules[0].direction == "out"
    assert rules.manual == {"abc123": "Leisure / Hobbies"}


def test_unclassified_is_biggest_absolute_first():
    rows = [tx("A", -5), tx("B", 50), tx("C", -500), tx("D", -9999)]
    apply(rows, Rules())
    rows[3]["group"] = "Shopping"
    assert [r["details"] for r in unclassified(rows)] == ["C", "B", "A"]


def test_suggested_pattern_escapes_details():
    assert suggested_pattern(tx("AMZ*MKTPLACE (UK)", -1)) == r"^AMZ\*MKTPLACE\ \(UK\)$"


def run_review(tmp_path, rows, categories, answers):
    path = tmp_path / "rules.toml"
    categories, answers = iter(categories), iter(answers)

    def reclassify():
        apply(rows, load_rules(path, TAXONOMY))

    def ask_category(prompt):
        try:
            return next(categories)
        except StopIteration:
            raise EOFError

    reclassify()
    try:  # ends when nothing is left, or when the scripted categories run out (like ctrl-d)
        review(rows, path, TAXONOMY, ask_category, lambda prompt: next(answers), reclassify, say=lambda *a: None)
    except EOFError:
        pass
    return load_rules(path, TAXONOMY)


def test_review_saves_a_rule_for_the_biggest_item_and_reclassifies(tmp_path):
    rows = [tx("TESCO STORES", -80), tx("TESCO STORES", -20), tx("TFL TRAVEL", -5)]
    rules = run_review(tmp_path, rows, ["Groceries / Supermarket"], ["r"])
    assert [r.patterns for r in rules.rules] == [{"details": r"^TESCO\ STORES$"}]
    assert [r["group"] for r in rows] == ["Groceries", "Groceries", "Uncategorised"]


def test_review_can_classify_one_transaction_or_use_an_edited_pattern(tmp_path):
    rows = [tx("JOHN LEWIS", -900, id_="sofa"), tx("JOHN LEWIS", -30), tx("TFL TRAVEL CH", -5), tx("TFL GOV", -4)]
    rules = run_review(
        tmp_path,
        rows,
        ["Shopping / Home & garden", "Shopping / Gifts given", "Transport / Public transport"],
        ["o", "r", "e", "^TFL", "y"],
    )
    assert rules.manual == {"sofa": "Shopping / Home & garden"}
    assert [r.patterns for r in rules.rules] == [{"details": r"^JOHN\ LEWIS$"}, {"details": "^TFL"}]
    assert all(r["group"] != "Uncategorised" for r in rows)


def test_review_skips_on_blank_and_rejects_unknown_category(tmp_path):
    rows = [tx("MYSTERY", -100), tx("TESCO", -10)]
    rules = run_review(tmp_path, rows, ["", "Not / Real", "Groceries / Supermarket"], ["r"])
    assert [r.patterns for r in rules.rules] == [{"details": r"^TESCO$"}]
    assert rows[0]["group"] == "Uncategorised"


def test_local_taxonomy_overrides_the_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert "Transport / Taxis" in load_taxonomy()
    (tmp_path / "taxonomy.toml").write_text('Mine = ["Only"]\n')
    assert load_taxonomy() == ["Mine / Only"]
