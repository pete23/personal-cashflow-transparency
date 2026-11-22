# personal-cashflow-transparency

Eat bank statements, excrete pivot tables. In no way an official product of any bank.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/cashflow scan path/to/statements
```

## Usage

```sh
.venv/bin/cashflow check path/to/statements                                    # missing or duplicate statements
.venv/bin/cashflow transactions path/to/statements -o data/transactions.json   # parse PDFs (slow; rerun when statements change)
.venv/bin/cashflow classify data/transactions.json                             # apply rules.toml, then review unclassified rows
.venv/bin/cashflow serve data/transactions.json --open                         # explore in a pivot table at http://127.0.0.1:8000/
```

`data/` and `rules.toml` hold personal data and are gitignored.
