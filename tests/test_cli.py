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
