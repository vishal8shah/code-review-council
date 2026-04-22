from __future__ import annotations

from unittest.mock import patch

from council.reporters.terminal import _rule_characters, _safe_text, print_verdict
from council.schemas import ChangedSymbol, ChairVerdict, ReviewPack


def test_safe_text_replaces_unencodable_characters_for_cp1252():
    with patch("council.reporters.terminal._console_encoding", return_value="cp1252"):
        assert _safe_text("arrow -> →") == "arrow -> ?"


def test_rule_characters_falls_back_to_ascii_for_cp1252():
    with patch("council.reporters.terminal._console_encoding", return_value="cp1252"):
        assert _rule_characters() == "-"


def test_print_verdict_sanitizes_skipped_file_names_for_cp1252(capsys):
    verdict = ChairVerdict(
        verdict="PASS",
        confidence=1.0,
        summary="Looks good.",
        rationale="All checks passed.",
    )
    review_pack = ReviewPack(
        diff_text="diff --git a/a.py b/a.py",
        changed_files=["a.py"],
        changed_symbols=[
            ChangedSymbol(
                name="run",
                kind="function",
                file="a.py",
                line_start=1,
                line_end=2,
                change_type="modified",
            )
        ],
        total_lines_changed=1,
        token_estimate=10,
        files_skipped=["tests/test_\u2192.py"],
    )

    with patch("council.reporters.terminal._console_encoding", return_value="cp1252"):
        print_verdict(verdict, review_pack=review_pack)

    output = capsys.readouterr().out
    assert "Skipped 1 files: tests/test_?.py" in output
    assert "Next steps" in output
