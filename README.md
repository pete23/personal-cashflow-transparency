# personal-cashflow-transparency

Eat bank statements, excrete pivot tables. In no way an official product of any bank.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/cashflow scan path/to/statements
```
