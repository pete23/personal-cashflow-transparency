"""Interactive review: classify the biggest unclassified transaction, save a rule, repeat."""

import re
from collections.abc import Callable
from pathlib import Path

from cashflow.rules import UNCATEGORISED, Rule, append_manual, append_rule

# The prompts the review loop needs; prompt_toolkit in a terminal, stubs in tests.
Ask = Callable[[str], str]


def unclassified(rows: list[dict], skipped: set[str] = frozenset()) -> list[dict]:
    """Unclassified transactions, biggest absolute amount first."""
    pending = [r for r in rows if r["kind"] == "transaction" and r["group"] == UNCATEGORISED and r["id"] not in skipped]
    return sorted(pending, key=lambda r: abs(r["amount"]), reverse=True)


def suggested_pattern(row: dict) -> str:
    return "^" + re.escape(row["details"].strip()) + "$"


def describe(row: dict) -> str:
    reference = f" | {row['reference']}" if row["reference"] else ""
    return f"{row['amount']:>12,.2f}  {row['date']}  {row['type']:<4} {row['details']}{reference}  [a/c …{row['account_number'][-4:]}]"


def summary(rows: list[dict]) -> str:
    txs = [r for r in rows if r["kind"] == "transaction"]
    left = [r for r in txs if r["group"] == UNCATEGORISED]
    total = sum(abs(r["amount"]) for r in txs) or 1
    remaining = sum(abs(r["amount"]) for r in left)
    return (
        f"{len(txs) - len(left)} of {len(txs)} transactions classified; "
        f"unclassified {len(left)} rows, £{remaining:,.0f} ({100 * remaining / total:.1f}% of money moved)"
    )


def review(rows: list[dict], rules_path: Path, taxonomy: list[str], ask_category: Ask, ask: Ask, reclassify: Callable[[], None], say=print) -> None:
    """Loop until quit or nothing is left. reclassify() reloads rules, reapplies them to rows and saves."""
    skipped: set[str] = set()
    while True:
        say("\n" + summary(rows))
        pending = unclassified(rows, skipped)
        if not pending:
            say("Nothing left to classify.")
            return
        row = pending[0]
        pattern = suggested_pattern(row)
        similar = [r for r in pending if Rule("", {"details": pattern}).matches(r)]
        say(describe(row))
        if len(similar) > 1:
            say(f"  {len(similar)} unclassified rows share these details, totalling £{sum(r['amount'] for r in similar):,.2f}")

        category = ask_category("category (blank to skip, ctrl-d to quit)> ").strip()
        if not category:
            skipped.add(row["id"])
            continue
        if category not in taxonomy:
            say(f"  unknown category {category!r}; pick one from the menu")
            continue

        while True:
            choice = ask(f"  [r]ule details ~ /{pattern}/ ({len(similar)} rows)  [e]dit pattern  [o]nly this one  [s]kip> ").strip().lower()
            if choice in ("", "r"):
                append_rule(rules_path, Rule(category, {"details": pattern}))
                break
            if choice == "o":
                append_manual(rules_path, row["id"], category)
                break
            if choice == "s":
                skipped.add(row["id"])
                break
            if choice == "e":
                edited = ask("  details regex (prefix 'reference:' or 'type:' to match another field)> ").strip()
                field, _, regex = edited.partition(":") if re.match(r"^(reference|type|details):", edited) else ("details", "", edited)
                try:
                    candidate = Rule(category, {field: regex.strip()})
                except re.error as e:
                    say(f"  bad regex: {e}")
                    continue
                hits = [r for r in pending if candidate.matches(r)]
                say(f"  matches {len(hits)} unclassified rows, e.g. " + "; ".join(r["details"] for r in hits[:3]))
                if hits and ask("  save this rule? [y/n]> ").strip().lower() in ("", "y"):
                    append_rule(rules_path, candidate)
                    break
        reclassify()
