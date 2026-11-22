"""Classify transactions into the taxonomy using a personal rules file.

The rules file is TOML holding two arrays of tables, both appended to as you classify:

    [[rule]]                       # first matching rule wins
    category = "Transport / Public transport"
    details = '^TFL'               # case-insensitive regexes searched in each field
    type = 'VIS|\\)\\)\\)'         # optional; also: reference, account (account number)
    direction = "out"              # optional: "in" or "out"

    [[manual]]                     # one transaction, by id; beats every rule
    id = "3f2a9c0d1e4b"
    category = "Shopping / Gifts given"
"""

import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

UNCATEGORISED = "Uncategorised"
MATCH_FIELDS = {"details": "details", "reference": "reference", "type": "type", "account": "account_number"}
BALANCE_KINDS = {"opening_balance": "Balance / Opening", "closing_balance": "Balance / Closing"}


LOCAL_TAXONOMY = Path("taxonomy.toml")


def load_taxonomy(path: Path | None = None) -> list[str]:
    """Load the given taxonomy, else a personal taxonomy.toml in the working directory, else the default."""
    if path is None and LOCAL_TAXONOMY.exists():
        path = LOCAL_TAXONOMY
    text = path.read_text() if path else resources.files("cashflow").joinpath("default_taxonomy.toml").read_text()
    return [f"{group} / {sub}" for group, subs in tomllib.loads(text).items() for sub in subs]


@dataclass
class Rule:
    category: str
    patterns: dict[str, str] = field(default_factory=dict)
    direction: str | None = None
    _compiled: dict[str, re.Pattern] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        self._compiled = {name: re.compile(p, re.IGNORECASE) for name, p in self.patterns.items()}

    def matches(self, row: dict) -> bool:
        if self.direction == "in" and not (row["amount"] or 0) > 0:
            return False
        if self.direction == "out" and not (row["amount"] or 0) < 0:
            return False
        return all(pattern.search(row[MATCH_FIELDS[name]] or "") for name, pattern in self._compiled.items())

    def describe(self) -> str:
        parts = [f"{name}~/{pattern}/" for name, pattern in self.patterns.items()]
        if self.direction:
            parts.append(self.direction)
        return " ".join(parts)


@dataclass
class Rules:
    rules: list[Rule] = field(default_factory=list)
    manual: dict[str, str] = field(default_factory=dict)

    def classify(self, row: dict) -> tuple[str, str]:
        """Return (category, how) for a row; how names the deciding rule."""
        if row["kind"] in BALANCE_KINDS:
            return BALANCE_KINDS[row["kind"]], "balance"
        if row["id"] in self.manual:
            return self.manual[row["id"]], "manual"
        for rule in self.rules:
            if rule.matches(row):
                return rule.category, rule.describe()
        return UNCATEGORISED, ""


def load_rules(path: Path, taxonomy: list[str]) -> Rules:
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    known = set(taxonomy)
    rules = Rules()
    for entry in data.get("rule", []):
        _check_category(entry["category"], known, path)
        patterns = {name: entry[name] for name in MATCH_FIELDS if name in entry}
        if not patterns:
            raise ValueError(f"{path}: rule for {entry['category']!r} has nothing to match on")
        rules.rules.append(Rule(entry["category"], patterns, entry.get("direction")))
    for entry in data.get("manual", []):
        _check_category(entry["category"], known, path)
        rules.manual[entry["id"]] = entry["category"]
    return rules


def _check_category(category: str, known: set[str], path: Path):
    if category not in known:
        raise ValueError(f"{path}: unknown category {category!r}")


def apply(rows: list[dict], rules: Rules) -> None:
    """Set group, subcategory and rule on every row in place."""
    for row in rows:
        category, how = rules.classify(row)
        row["group"], _, row["subcategory"] = category.partition(" / ")
        row["rule"] = how


def append_rule(path: Path, rule: Rule) -> None:
    lines = ["", "[[rule]]", f"category = {_toml_string(rule.category)}"]
    lines += [f"{name} = {_toml_string(pattern)}" for name, pattern in rule.patterns.items()]
    if rule.direction:
        lines.append(f"direction = {_toml_string(rule.direction)}")
    _append(path, lines)


def append_manual(path: Path, transaction_id: str, category: str) -> None:
    _append(path, ["", "[[manual]]", f"id = {_toml_string(transaction_id)}", f"category = {_toml_string(category)}"])


def _append(path: Path, lines: list[str]) -> None:
    with path.open("a") as f:
        f.write("\n".join(lines) + "\n")


def _toml_string(value: str) -> str:
    # Literal strings keep regex backslashes readable; fall back to an escaped basic string.
    if "'" not in value and "\n" not in value:
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
