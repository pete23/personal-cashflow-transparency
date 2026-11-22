import json
import threading
import urllib.error
import urllib.request

import pytest

from cashflow.pivot import pivot_rows
from cashflow.serve import make_server

ROWS = [
    {"kind": "opening_balance", "date": "2025-12-02", "amount": None, "balance": 100.0},
    {
        "id": "a1",
        "kind": "transaction",
        "date": "2026-01-15",
        "type": "VIS",
        "details": "TESCO",
        "reference": "CROYDON",
        "amount": -12.5,
        "sort_code": "00-11-22",
        "account_number": "12345678",
        "source": "2026-02-02_Statement.pdf",
        "group": "Groceries",
        "subcategory": "Supermarket",
        "rule": "details~/^TESCO/",
    },
]


def test_pivot_rows_derive_date_fields_and_skip_balances():
    [record] = pivot_rows(ROWS)
    assert record["Year"] == "2026"
    assert record["Year-Month"] == "2026-01"
    assert record["Month"] == "Jan"
    assert (record["Group"], record["Subcategory"], record["Amount"], record["Direction"]) == ("Groceries", "Supermarket", -12.5, "Out")
    assert record["Account"] == "00-11-22 12345678"


def test_unclassified_rows_get_the_uncategorised_group():
    row = {k: v for k, v in ROWS[1].items() if k not in ("group", "subcategory", "rule")}
    [record] = pivot_rows([row])
    assert (record["Group"], record["Subcategory"]) == ("Uncategorised", "(unclassified)")


@pytest.fixture
def server(tmp_path):
    path = tmp_path / "transactions.json"
    path.write_text(json.dumps(ROWS))
    httpd = make_server(path, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url):
    with urllib.request.urlopen(url) as response:
        return response.headers["Content-Type"], response.read()


def test_serves_page_vendored_libraries_and_data(server):
    content_type, body = get(server + "/")
    assert content_type.startswith("text/html") and b"pivotUI" in body
    for name in ("pivot.min.js", "subtotal.min.js", "jquery.min.js", "jquery-ui.min.js", "pivot.min.css", "subtotal.min.css"):
        content_type, body = get(f"{server}/vendor/{name}")
        assert body, name
    content_type, body = get(server + "/transactions.json")
    assert content_type.startswith("application/json")
    assert [r["Details"] for r in json.loads(body)] == ["TESCO"]


@pytest.mark.parametrize("path", ["/../pyproject.toml", "/vendor/../../cli.py", "/rules.py", "/vendor/README.md", "/nope.js"])
def test_refuses_anything_but_known_static_files(server, path):
    with pytest.raises(urllib.error.HTTPError) as error:
        get(server + path)
    assert error.value.code == 404
