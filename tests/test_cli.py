from cashflow.cli import main
from cashflow.scan import find_files


def make_tree(root):
    (root / "acct-b").mkdir()
    (root / "acct-b" / "2026-02.pdf").write_text("")
    (root / "acct-a").mkdir()
    (root / "acct-a" / "2026-01.pdf").write_text("")
    (root / ".DS_Store").write_text("")
    (root / ".cache").mkdir()
    (root / ".cache" / "ignored.pdf").write_text("")


def test_find_files_is_recursive_sorted_and_skips_hidden(tmp_path):
    make_tree(tmp_path)
    found = [p.relative_to(tmp_path).as_posix() for p in find_files(tmp_path)]
    assert found == ["acct-a/2026-01.pdf", "acct-b/2026-02.pdf"]


def test_scan_prints_relative_paths(tmp_path, capsys):
    make_tree(tmp_path)
    assert main(["scan", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == ["acct-a/2026-01.pdf", "acct-b/2026-02.pdf"]


def test_scan_rejects_missing_directory(tmp_path, capsys):
    assert main(["scan", str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_transactions_writes_json_and_flags_unreconciled(tmp_path, monkeypatch, capsys):
    import json

    from cashflow import cli
    from test_bank_h import statement

    (tmp_path / "good.pdf").write_text("")
    (tmp_path / "notes.txt").write_text("")
    monkeypatch.setattr(cli, "pdf_to_text", lambda path: statement())
    out = tmp_path / "out.json"

    assert main(["transactions", str(tmp_path), "-o", str(out)]) == 0
    rows = json.loads(out.read_text())
    assert {r["source"] for r in rows} == {"good.pdf"}
    assert rows[1]["amount"] == -40.0 and rows[1]["date"] == "2025-12-03"

    monkeypatch.setattr(cli, "pdf_to_text", lambda path: statement().replace("1,100.50", "1,100.00"))
    assert main(["transactions", str(tmp_path), "-o", str(out)]) == 1
    assert "good.pdf: 2026-01-01 LANDLORD: running balance -50.00 but statement shows -50.50" in capsys.readouterr().err


def test_check_reports_duplicates_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    from cashflow import cli
    from test_bank_h import statement

    (tmp_path / "dec.pdf").write_text("")
    (tmp_path / "dec-2.pdf").write_text("")
    monkeypatch.setattr(cli, "pdf_to_text", lambda path: statement())

    assert main(["check", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "00-11-22 12345678" in out and "2 statements, 2025-12-03 to 2026-01-02" in out
    assert "duplicate: dec-2.pdf repeats dec.pdf" in out


def test_transactions_skips_duplicate_statements(tmp_path, monkeypatch, capsys):
    import json

    from cashflow import cli
    from test_bank_h import statement

    (tmp_path / "dec.pdf").write_text("")
    (tmp_path / "dec-2.pdf").write_text("")
    monkeypatch.setattr(cli, "pdf_to_text", lambda path: statement())
    out = tmp_path / "out.json"

    assert main(["transactions", str(tmp_path), "-o", str(out)]) == 0
    assert {r["source"] for r in json.loads(out.read_text())} == {"dec.pdf"}
    assert "dec-2.pdf repeats dec.pdf (skipped)" in capsys.readouterr().err


def test_classify_and_serve_default_to_data_transactions_json():
    from cashflow.cli import DEFAULT_TRANSACTIONS, build_parser

    parser = build_parser()
    for command in ("classify", "serve"):
        assert parser.parse_args([command]).transactions == DEFAULT_TRANSACTIONS
    assert parser.parse_args(["serve"]).no_open is False
    assert parser.parse_args(["transactions", "statements"]).output == DEFAULT_TRANSACTIONS


def test_missing_transactions_file_says_how_to_make_one(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["classify"]) == 2
    assert "run `cashflow transactions <statements directory>` first" in capsys.readouterr().err


def test_serve_falls_back_to_a_free_port_and_opens_the_browser(tmp_path, monkeypatch, capsys):
    import socket
    import webbrowser

    from cashflow import serve

    path = tmp_path / "transactions.json"
    path.write_text("[]")
    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)

    def stop(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(serve.LocalServer, "serve_forever", stop)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert main(["serve", str(path), "--port", str(taken)]) == 0
    [url] = opened
    assert url.startswith("http://127.0.0.1:") and f":{taken}/" not in url
    assert url in capsys.readouterr().out


def test_serve_on_all_interfaces_shows_lan_address_and_warns(tmp_path, monkeypatch, capsys):
    import webbrowser

    from cashflow import cli, serve

    path = tmp_path / "transactions.json"
    path.write_text("[]")
    opened, bound = [], []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    monkeypatch.setattr(cli, "lan_address", lambda: "192.168.1.20")
    real_make_server = serve.make_server

    def record(transactions, port, host="127.0.0.1"):
        bound.append(host)
        return real_make_server(transactions, 0, "127.0.0.1")  # don't open a real LAN socket in tests

    monkeypatch.setattr(cli, "make_server", record)
    monkeypatch.setattr(serve.LocalServer, "serve_forever", lambda self: (_ for _ in ()).throw(KeyboardInterrupt))

    assert main(["serve", str(path), "--host", "0.0.0.0"]) == 0
    out = capsys.readouterr().out
    assert bound == ["0.0.0.0"]
    assert "On your network: http://192.168.1.20:" in out and "Warning: anyone who can reach" in out
    assert opened[0].startswith("http://127.0.0.1:")


def test_serve_defaults_to_loopback_without_warning(tmp_path, monkeypatch, capsys):
    import webbrowser

    from cashflow import serve

    path = tmp_path / "transactions.json"
    path.write_text("[]")
    monkeypatch.setattr(webbrowser, "open", lambda url: None)
    monkeypatch.setattr(serve.LocalServer, "serve_forever", lambda self: (_ for _ in ()).throw(KeyboardInterrupt))
    assert main(["serve", str(path), "--port", "0"]) == 0
    assert "Warning" not in capsys.readouterr().out
