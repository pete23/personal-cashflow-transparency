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
.venv/bin/cashflow check path/to/statements          # missing or duplicate statements
.venv/bin/cashflow transactions path/to/statements   # parse PDFs into data/transactions.json (slow; rerun when statements change)
.venv/bin/cashflow classify                          # apply rules.toml, then review unclassified rows
.venv/bin/cashflow serve                             # explore in a pivot table; opens your browser
```

`serve` listens on this machine only. `--host 0.0.0.0` makes it reachable from your network, with no login or encryption: anyone who can reach it can read your transactions.

`data/`, `rules.toml` and `taxonomy.toml` hold personal data and are gitignored. `classify` uses `./taxonomy.toml` if present, otherwise the built-in default; copy `src/cashflow/default_taxonomy.toml` to start your own.

## Licence

This project is licensed under the GNU General Public License v3.0; see [LICENSE](LICENSE).

It includes third-party front-end libraries in [`src/cashflow/static/vendor/`](src/cashflow/static/vendor/), which remain under their own MIT licences: PivotTable.js, subtotal.js, jQuery and jQuery UI. Each licence is kept alongside its library, and the vendor [README](src/cashflow/static/vendor/README.md) lists versions and sources.
