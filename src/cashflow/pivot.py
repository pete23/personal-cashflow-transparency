"""Shape classified transactions into flat records for PivotTable.js."""

from datetime import date

from cashflow.rules import UNCATEGORISED


def pivot_rows(rows: list[dict]) -> list[dict]:
    """One record per transaction with display-friendly field names and derived date fields.

    Opening and closing balance rows are left out: their balances don't sum.
    """
    records = []
    for row in rows:
        if row["kind"] != "transaction":
            continue
        when = date.fromisoformat(row["date"])
        records.append(
            {
                "Group": row.get("group", UNCATEGORISED),
                "Subcategory": row.get("subcategory") or "(unclassified)",
                "Year": str(when.year),
                "Year-Month": f"{when:%Y-%m}",
                "Month": f"{when:%b}",
                "Date": row["date"],
                "Amount": row["amount"],
                "Direction": "In" if row["amount"] > 0 else "Out",
                "Account": f"{row['sort_code']} {row['account_number']}",
                "Type": row["type"],
                "Details": row["details"],
                "Reference": row["reference"],
                "Statement": row["source"],
                "Rule": row.get("rule", ""),
            }
        )
    return records
