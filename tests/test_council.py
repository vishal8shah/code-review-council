"""Tests for the Code Review Council — validates the full pipeline.

Tests run WITHOUT real LLM calls by mocking litellm.acompletion.
"""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from council.schemas import (
    ChangedSymbol,
    ChairFinding,
    ChairVerdict,
    DiffContext,
    DiffFile,
    DiffHunk,
    Finding,
    GateZeroFinding,
    GateZeroResult,
    ReviewerOutput,
    ReviewPack,
)
from council.config import CouncilConfig, load_config
from council.diff_parser import parse_diff, detect_language
from council.gate_zero import check, check_secrets, check_readme_updated, check_file_size
from council.diff_preprocessor import process, _should_ignore, _is_generated, _file_priority
from council.review_pack import assemble, _extract_python_symbols, _build_test_coverage_map, _filter_to_changed_symbols, _extract_deleted_symbols
from council.analyzers.python import PythonAnalyzer
from council.analyzers.registry import get_analyzer
from council.reviewers.base import BaseReviewer
from council.reviewers.secops import SecOpsReviewer
from council.chair import synthesize, _build_chair_message


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DIFF = """\
diff --git a/src/parser.py b/src/parser.py
new file mode 100644
--- /dev/null
+++ b/src/parser.py
@@ -0,0 +1,25 @@
+\"\"\"XML parser module.\"\"\"
+
+import xml.etree.ElementTree as ET
+
+
+def parse_node(xml_string: str) -> dict:
+    \"\"\"Parse an XML string into a dictionary.\"\"\"
+    root = ET.fromstring(xml_string)
+    return {child.tag: child.text for child in root}
+
+
+def validate_schema(data, schema):
+    for key in schema:
+        if key not in data:
+            return False
+    return True
+
+
+class XMLHandler:
+    \"\"\"Handles XML parsing and validation.\"\"\"
+
+    def process(self, raw: str) -> dict:
+        \"\"\"Process raw XML input.\"\"\"
+        parsed = parse_node(raw)
+        return parsed
"""

SAMPLE_DIFF_WITH_SECRET = """\
diff --git a/config/settings.py b/config/settings.py
index 1234567..abcdefg 100644
--- a/config/settings.py
+++ b/config/settings.py
@@ -1,2 +1,4 @@
 # Settings
+API_KEY = 'AKIAIOSFODNN7EXAMPLE'
+SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
 DEBUG = True
"""

SAMPLE_PYTHON_SOURCE = '''\
"""Module docstring."""

def public_function(x: int) -> str:
    """Documented function."""
    return str(x)

def undocumented_function(y):
    return y + 1

class MyClass:
    """Documented class."""
    
    def public_method(self, z: int) -> None:
        """Documented method."""
        pass
    
    def _private_method(self):
        pass
'''


def _make_diff_context(**overrides) -> DiffContext:
    """Helper to create a DiffContext for testing."""
    defaults = {
        "files": [
            DiffFile(
                path="src/parser.py",
                language="python",
                change_type="added",
                additions=25,
                deletions=0,
                hunks=[DiffHunk(
                    source_start=0, source_length=0,
                    target_start=1, target_length=25,
                    content=SAMPLE_DIFF,
                )],
                source_content=None,
            )
        ],
        "changed_files": ["src/parser.py"],
        "added_files": ["src/parser.py"],
        "deleted_files": [],
        "branch": "feature/parser",
        "total_additions": 25,
        "total_deletions": 0,
    }
    defaults.update(overrides)
    return DiffContext(**defaults)


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------

class TestSchemas:
    """Verify Pydantic models validate correctly."""

    def test_finding_with_evidence(self):
        """Finding accepts all v1.2 evidence fields."""
        f = Finding(
            severity="HIGH",
            category="security",
            file="auth.py",
            line_start=10,
            line_end=25,
            symbol_name="handle_login",
            symbol_kind="function",
            description="SQL injection risk",
            suggestion="Use parameterized queries",
            evidence_ref="diff hunk 2 shows string concatenation with user input",
            policy_id="security.sql_injection",
            confidence=0.95,
        )
        assert f.severity == "HIGH"
        assert f.evidence_ref is not None
        assert f.confidence == 0.95

    def test_chair_verdict_with_accepted_dismissed(self):
        """ChairVerdict supports accepted_blockers and dismissed_findings."""
        v = ChairVerdict(
            verdict="FAIL",
            confidence=0.9,
            degraded=False,
            summary="Critical security issue found.",
            accepted_blockers=[
                ChairFinding(
                    severity="CRITICAL", category="security",
                    file="auth.py", description="SQL injection",
                    suggestion="Fix", chair_action="accepted",
                    chair_reasoning="Evidence-backed",
                    source_reviewers=["secops"],
                )
            ],
            dismissed_findings=[
                ChairFinding(
                    severity="HIGH", category="style",
                    file="utils.py", description="Naming convention",
                    suggestion="Rename", chair_action="dismissed",
                    chair_reasoning="Stylistic preference, no policy",
                )
            ],
            all_findings=[],
            reviewer_agreement_score=0.8,
            rationale="SecOps found a confirmed SQL injection.",
        )
        assert v.verdict == "FAIL"
        assert len(v.accepted_blockers) == 1
        assert len(v.dismissed_findings) == 1
        assert v.accepted_blockers[0].chair_action == "accepted"

    def test_gate_zero_early_exit(self):
        """GateZeroResult.as_early_exit() produces a valid ChairVerdict."""
        result = GateZeroResult(
            passed=False,
            hard_fail=True,
            findings=[
                GateZeroFinding(
                    check="secret", severity="CRITICAL", category="security",
                    file="config.py", line_start=5,
                    message="AWS key detected",
                )
            ],
        )
        verdict = result.as_early_exit()
        assert verdict.verdict == "FAIL"
        assert verdict.confidence == 1.0
        assert len(verdict.accepted_blockers) == 1

    def test_review_pack_structure(self):
        """ReviewPack accepts all fields."""
        rp = ReviewPack(
            diff_text="some diff",
            changed_files=["a.py"],
            changed_symbols=[
                ChangedSymbol(
                    name="foo", kind="function", file="a.py",
                    line_start=1, line_end=5, change_type="added",
                    has_tests=False,
                )
            ],
            test_coverage_map={"a.py": []},
            languages_detected=["python"],
        )
        assert rp.changed_symbols[0].has_tests is False

    def test_reviewer_output_with_error(self):
        """ReviewerOutput supports error field for degraded mode."""
        o = ReviewerOutput(
            reviewer_id="secops", model="test", verdict="PASS",
            confidence=0.0, error="Timeout after 60s",
        )
        assert o.error is not None


# ---------------------------------------------------------------------------
# Config Tests
# ---------------------------------------------------------------------------

class TestConfig:
    """Configuration loading."""

    def test_default_config(self, tmp_path):
        """Loading from a directory without .council.toml produces defaults."""
        config = load_config(tmp_path)
        assert config.chair_model == "openai/gpt-4o"
        assert config.gate_zero.require_docs is True
        assert config.gate_zero.check_secrets is True
        assert len(config.reviewers) > 0

    def test_load_toml_config(self, tmp_path):
        """Custom .council.toml overrides defaults."""
        toml = tmp_path / ".council.toml"
        toml.write_text("""
[council]
chair_model = "anthropic/claude-opus-4-6"
timeout_seconds = 30

[gate_zero]
require_docs = false
check_secrets = true

[[reviewers]]
id = "secops"
name = "SecOps"
model = "anthropic/claude-sonnet-4-20250514"
enabled = true
""")
        config = load_config(tmp_path)
        assert config.chair_model == "anthropic/claude-opus-4-6"
        assert config.timeout_seconds == 30
        assert config.gate_zero.require_docs is False
        assert len(config.reviewers) == 1

    def test_active_reviewers_filters_disabled(self):
        """active_reviewers property filters out disabled reviewers."""
        from council.config import ReviewerConfig
        config = CouncilConfig(reviewers=[
            ReviewerConfig(id="a", name="A", model="m", enabled=True),
            ReviewerConfig(id="b", name="B", model="m", enabled=False),
        ])
        assert len(config.active_reviewers) == 1
        assert config.active_reviewers[0].id == "a"


# ---------------------------------------------------------------------------
# Diff Parser Tests
# ---------------------------------------------------------------------------

class TestDiffParser:
    """Diff parsing."""

    def test_parse_basic_diff(self):
        """Parse a simple unified diff into DiffContext."""
        ctx = parse_diff(SAMPLE_DIFF, load_content=False)
        assert len(ctx.files) == 1
        assert ctx.files[0].path == "src/parser.py"
        assert ctx.files[0].change_type == "added"
        assert ctx.total_additions > 0
        assert "src/parser.py" in ctx.added_files

    def test_empty_diff(self):
        """Empty diff returns empty context."""
        ctx = parse_diff("", load_content=False)
        assert len(ctx.files) == 0

    def test_detect_language(self):
        """File extension detection."""
        assert detect_language("app.py") == "python"
        assert detect_language("index.ts") == "typescript"
        assert detect_language("style.css") is None


# ---------------------------------------------------------------------------
# Gate Zero Tests
# ---------------------------------------------------------------------------

class TestGateZero:
    """Deterministic static checks."""

    def test_secret_detection(self):
        """Detects AWS keys in diff content."""
        ctx = parse_diff(SAMPLE_DIFF_WITH_SECRET, load_content=False)
        findings = check_secrets(ctx)
        assert len(findings) >= 1
        assert any(f.severity == "CRITICAL" for f in findings)
        assert any("key" in f.message.lower() for f in findings)

    def test_no_false_positive_secrets(self):
        """Clean diff produces no secret findings."""
        ctx = _make_diff_context()
        findings = check_secrets(ctx)
        assert len(findings) == 0

    def test_readme_check_fires(self):
        """New public module without README update triggers finding."""
        from council.config import GateZeroConfig
        gc = GateZeroConfig()
        ctx = DiffContext(
            files=[DiffFile(path="src/newmodule.py", change_type="added", additions=50)],
            changed_files=["src/newmodule.py"],
            added_files=["src/newmodule.py"],
        )
        findings = check_readme_updated(ctx, gc)
        assert len(findings) == 1
        assert findings[0].severity == "HIGH"

    def test_readme_check_passes(self):
        """New module + README update = no finding."""
        from council.config import GateZeroConfig
        gc = GateZeroConfig()
        ctx = DiffContext(
            files=[
                DiffFile(path="src/newmodule.py", change_type="added", additions=50),
                DiffFile(path="README.md", change_type="modified"),
            ],
            changed_files=["src/newmodule.py", "README.md"],
            added_files=["src/newmodule.py"],
        )
        findings = check_readme_updated(ctx, gc)
        assert len(findings) == 0

    def test_file_size_check(self):
        """Oversized file triggers finding."""
        from council.config import GateZeroConfig
        gc = GateZeroConfig(max_file_lines=100)
        ctx = DiffContext(
            files=[DiffFile(path="huge.py", change_type="added", additions=500)],
        )
        findings = check_file_size(ctx, gc)
        assert len(findings) == 1

    def test_full_gate_zero_hard_fail(self):
        """Gate Zero with secret = hard fail."""
        ctx = parse_diff(SAMPLE_DIFF_WITH_SECRET, load_content=False)
        config = CouncilConfig()
        result = check(ctx, config)
        assert result.hard_fail is True
        assert result.passed is False


# ---------------------------------------------------------------------------
# Python Analyzer Tests
# ---------------------------------------------------------------------------

class TestPythonAnalyzer:
    """Language-specific static analysis."""

    def test_docstring_detection(self):
        """Finds missing docstrings on public functions."""
        analyzer = PythonAnalyzer()
        findings = analyzer.check_docs(SAMPLE_PYTHON_SOURCE, "test.py")
        # undocumented_function should be flagged
        names = [f.message for f in findings]
        assert any("undocumented_function" in m for m in names)
        # Documented ones should NOT be flagged
        assert not any("public_function" in m for m in names)
        assert not any("MyClass" in m for m in names)
        # Private method should NOT be flagged
        assert not any("_private_method" in m for m in names)

    def test_type_hint_detection(self):
        """Finds missing type annotations."""
        analyzer = PythonAnalyzer()
        findings = analyzer.check_types(SAMPLE_PYTHON_SOURCE, "test.py")
        # undocumented_function is missing return type and param type
        messages = " ".join(f.message for f in findings)
        assert "undocumented_function" in messages

    def test_analyzer_registry(self):
        """Registry returns PythonAnalyzer for .py files."""
        analyzer = get_analyzer("app.py")
        assert isinstance(analyzer, PythonAnalyzer)
        assert get_analyzer("style.css") is None


# ---------------------------------------------------------------------------
# Diff Preprocessor Tests
# ---------------------------------------------------------------------------

class TestDiffPreprocessor:
    """Filtering, prioritization, and token budgets."""

    def test_ignore_lockfiles(self):
        """package-lock.json is ignored."""
        assert _should_ignore("package-lock.json", ["package-lock.json"]) is True
        assert _should_ignore("src/app.py", ["package-lock.json"]) is False

    def test_ignore_directory_patterns(self):
        """vendor/ directory pattern matches."""
        assert _should_ignore("vendor/lib/foo.js", ["vendor/"]) is True
        assert _should_ignore("src/vendor_utils.py", ["vendor/"]) is False

    def test_ignore_wildcard_patterns(self):
        """*.min.js matches minified files."""
        assert _should_ignore("dist/app.min.js", ["*.min.js"]) is True
        assert _should_ignore("src/app.js", ["*.min.js"]) is False

    def test_generated_file_detection(self):
        """Files with @generated marker are detected."""
        f = DiffFile(
            path="gen.py", change_type="added",
            source_content="# @generated\ndef foo(): pass\n"
        )
        assert _is_generated(f) is True

        f2 = DiffFile(path="real.py", change_type="added", source_content="def foo(): pass\n")
        assert _is_generated(f2) is False

    def test_file_priority(self):
        """Security files get highest priority."""
        auth = DiffFile(path="src/auth.py", language="python", change_type="modified")
        util = DiffFile(path="src/utils.py", language="python", change_type="modified")
        test = DiffFile(path="tests/test_utils.py", language="python", change_type="modified")
        readme = DiffFile(path="README.md", language="markdown", change_type="modified")

        assert _file_priority(auth) > _file_priority(util)
        assert _file_priority(util) > _file_priority(test)
        assert _file_priority(test) > _file_priority(readme)

    def test_process_filters_and_budgets(self, tmp_path):
        """Process removes ignored files and respects token budget."""
        from council.config import PreprocessorConfig
        # Create a .councilignore
        (tmp_path / ".councilignore").write_text("package-lock.json\n")

        ctx = DiffContext(
            files=[
                DiffFile(
                    path="package-lock.json", change_type="modified", additions=10000,
                    hunks=[DiffHunk(source_start=1, source_length=0, target_start=1,
                                   target_length=10000, content="x" * 10000)],
                ),
                DiffFile(
                    path="src/app.py", language="python", change_type="modified", additions=50,
                    hunks=[DiffHunk(source_start=1, source_length=10, target_start=1,
                                   target_length=50, content="y" * 200)],
                ),
            ],
            changed_files=["package-lock.json", "src/app.py"],
        )

        config = PreprocessorConfig()
        processed, skipped, truncated = process(ctx, config, repo_root=tmp_path)

        assert "package-lock.json" in skipped
        assert "src/app.py" in processed.changed_files


# ---------------------------------------------------------------------------
# ReviewPack Tests
# ---------------------------------------------------------------------------

class TestReviewPack:
    """ReviewPack assembly."""

    def test_extract_python_symbols(self):
        """Extracts functions and classes from Python source."""
        symbols = _extract_python_symbols(SAMPLE_PYTHON_SOURCE, "test.py")
        names = {s.name for s in symbols}
        assert "public_function" in names
        assert "undocumented_function" in names
        assert "MyClass" in names
        assert "public_method" in names
        # Private methods included (they're methods, not top-level)
        assert "_private_method" in names

    def test_symbol_signatures(self):
        """Extracted symbols include correct signatures."""
        symbols = _extract_python_symbols(SAMPLE_PYTHON_SOURCE, "test.py")
        pub_fn = next(s for s in symbols if s.name == "public_function")
        assert "x: int" in pub_fn.signature
        assert "-> str" in pub_fn.signature

    def test_test_coverage_map(self):
        """Maps source files to test files by naming convention."""
        ctx = DiffContext(files=[
            DiffFile(path="src/parser.py", change_type="modified"),
            DiffFile(path="tests/test_parser.py", change_type="modified"),
            DiffFile(path="src/utils.py", change_type="modified"),
        ])
        m = _build_test_coverage_map(ctx)
        assert "tests/test_parser.py" in m.get("src/parser.py", [])
        assert m.get("src/utils.py") == []

    def test_assemble_full(self):
        """Full assembly produces a complete ReviewPack."""
        ctx = DiffContext(
            files=[
                DiffFile(
                    path="src/app.py", language="python", change_type="added",
                    additions=10, source_content=SAMPLE_PYTHON_SOURCE,
                    hunks=[DiffHunk(source_start=0, source_length=0,
                                   target_start=1, target_length=20,
                                   content=SAMPLE_PYTHON_SOURCE)],
                ),
            ],
            changed_files=["src/app.py"],
            added_files=["src/app.py"],
            branch="feature/test",
        )
        config = CouncilConfig()
        rp = assemble(ctx, gate_zero_findings=[], config=config)

        assert len(rp.changed_symbols) > 0
        assert "python" in rp.languages_detected
        assert rp.branch == "feature/test"
        assert rp.token_estimate > 0


# ---------------------------------------------------------------------------
# Reviewer Tests
# ---------------------------------------------------------------------------

class TestReviewers:
    """LLM reviewer personas."""

    def test_secops_has_prompt(self):
        """SecOps reviewer provides a security-focused system prompt."""
        r = SecOpsReviewer(reviewer_id="secops", model="test")
        prompt = r.get_system_prompt()
        assert "security" in prompt.lower()
        assert "injection" in prompt.lower()

    def test_user_message_contains_review_pack(self):
        """User message includes symbols and test map from ReviewPack."""
        r = BaseReviewer(reviewer_id="test", model="test")
        rp = ReviewPack(
            diff_text="+ some code",
            changed_symbols=[
                ChangedSymbol(
                    name="foo", kind="function", file="a.py",
                    line_start=1, line_end=5, change_type="added",
                    signature="def foo(x: int) -> str", has_tests=False,
                )
            ],
            test_coverage_map={"a.py": []},
            languages_detected=["python"],
        )
        msg = r._build_user_message(rp)
        assert "foo" in msg
        assert "NO tests" in msg
        assert "a.py" in msg

    @pytest.mark.asyncio
    async def test_reviewer_handles_error(self):
        """Reviewer gracefully handles LLM call failure."""
        r = SecOpsReviewer(reviewer_id="secops", model="test/nonexistent")
        rp = ReviewPack(diff_text="+ code")
        with patch("council.reviewers.base.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=TimeoutError("timeout"))
            output = await r.review(rp)
        assert output.error is not None
        assert output.confidence == 0.0

    @pytest.mark.asyncio
    async def test_reviewer_parses_valid_response(self):
        """Reviewer parses a well-formed LLM JSON response."""
        r = SecOpsReviewer(reviewer_id="secops", model="test")
        rp = ReviewPack(diff_text="+ code")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "verdict": "FAIL",
            "confidence": 0.9,
            "findings": [{
                "severity": "CRITICAL",
                "category": "security",
                "file": "auth.py",
                "line_start": 23,
                "description": "SQL injection via string concat",
                "suggestion": "Use parameterized queries",
                "evidence_ref": "Line 23: f'SELECT * FROM users WHERE id={user_id}'",
                "confidence": 0.95,
            }],
            "reasoning": "Clear SQL injection pattern",
        })
        mock_response.usage = MagicMock(total_tokens=500)

        with patch("council.reviewers.base.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            output = await r.review(rp)

        assert output.verdict == "FAIL"
        assert len(output.findings) == 1
        assert output.findings[0].severity == "CRITICAL"
        assert output.findings[0].evidence_ref is not None


# ---------------------------------------------------------------------------
# Chair Tests
# ---------------------------------------------------------------------------

class TestChair:
    """Council Chair synthesis."""

    def test_chair_message_includes_context(self):
        """Chair message includes ReviewPack summary and reviewer outputs."""
        rp = ReviewPack(
            diff_text="+ code",
            changed_files=["a.py"],
            changed_symbols=[
                ChangedSymbol(
                    name="foo", kind="function", file="a.py",
                    line_start=1, line_end=5, change_type="added",
                    has_tests=False,
                )
            ],
            languages_detected=["python"],
            total_lines_changed=20,
        )
        reviews = [
            ReviewerOutput(
                reviewer_id="secops", model="test", verdict="PASS",
                confidence=0.9, findings=[],
            )
        ]
        msg = _build_chair_message(rp, reviews)
        assert "foo" in msg
        assert "NO tests" in msg
        assert "secops" in msg

    @pytest.mark.asyncio
    async def test_chair_fast_pass(self):
        """No findings from any reviewer → fast PASS."""
        rp = ReviewPack(diff_text="+ code")
        reviews = [
            ReviewerOutput(reviewer_id="secops", model="m", verdict="PASS", confidence=0.9),
            ReviewerOutput(reviewer_id="qa", model="m", verdict="PASS", confidence=0.8),
        ]
        verdict = await synthesize(rp, reviews)
        assert verdict.verdict == "PASS"
        assert verdict.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_chair_degraded_pass(self):
        """No findings but degraded → PASS with lower confidence."""
        rp = ReviewPack(diff_text="+ code")
        reviews = [
            ReviewerOutput(reviewer_id="secops", model="m", verdict="PASS", confidence=0.9),
            ReviewerOutput(
                reviewer_id="qa", model="m", verdict="PASS",
                confidence=0.0, error="Timeout",
            ),
        ]
        verdict = await synthesize(rp, reviews, degraded=True)
        assert verdict.verdict == "PASS"
        assert verdict.degraded is True
        assert verdict.confidence < 0.95

    @pytest.mark.asyncio
    async def test_chair_synthesizes_llm_response(self):
        """Chair correctly parses an LLM FAIL verdict."""
        rp = ReviewPack(diff_text="+ code", changed_files=["a.py"])
        reviews = [
            ReviewerOutput(
                reviewer_id="secops", model="m", verdict="FAIL",
                confidence=0.95,
                findings=[Finding(
                    severity="CRITICAL", category="security", file="a.py",
                    description="SQL injection", suggestion="Fix",
                    evidence_ref="line 23",
                )],
            ),
        ]

        chair_response = json.dumps({
            "verdict": "FAIL",
            "confidence": 0.95,
            "degraded": False,
            "summary": "Critical security issue found.",
            "accepted_blockers": [{
                "severity": "CRITICAL",
                "category": "security",
                "file": "a.py",
                "description": "SQL injection",
                "suggestion": "Use parameterized queries",
                "evidence_ref": "line 23",
                "chair_action": "accepted",
                "chair_reasoning": "SecOps flagged with clear evidence",
                "source_reviewers": ["secops"],
                "consensus": False,
            }],
            "dismissed_findings": [],
            "all_findings": [],
            "reviewer_agreement_score": 1.0,
            "rationale": "Confirmed SQL injection vulnerability.",
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = chair_response
        mock_response.usage = MagicMock(total_tokens=1000)

        with patch("council.chair.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            verdict = await synthesize(rp, reviews)

        assert verdict.verdict == "FAIL"
        assert len(verdict.accepted_blockers) == 1
        assert verdict.accepted_blockers[0].chair_action == "accepted"

    @pytest.mark.asyncio
    async def test_chair_handles_error(self):
        """Chair LLM failure → fail closed."""
        rp = ReviewPack(diff_text="+ code")
        reviews = [
            ReviewerOutput(
                reviewer_id="secops", model="m", verdict="FAIL",
                confidence=0.9,
                findings=[Finding(
                    severity="HIGH", category="security", file="a.py",
                    description="issue", suggestion="fix",
                )],
            ),
        ]

        with patch("council.chair.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=Exception("API error"))
            verdict = await synthesize(rp, reviews)

        assert verdict.verdict == "FAIL"
        assert verdict.degraded is True
        assert "failed" in verdict.summary.lower()


# ---------------------------------------------------------------------------
# End-to-End Orchestrator Test
# ---------------------------------------------------------------------------

class TestOrchestrator:
    """Full pipeline integration test."""

    @pytest.mark.asyncio
    async def test_empty_diff_passes(self):
        """Empty diff → PASS."""
        from council.orchestrator import run_council
        result = await run_council(diff_text="")
        assert result.verdict.verdict == "PASS"

    @pytest.mark.asyncio
    async def test_secret_in_diff_hard_fails(self):
        """Secret in diff → Gate Zero hard fail, no LLM calls."""
        from council.orchestrator import run_council
        result = await run_council(diff_text=SAMPLE_DIFF_WITH_SECRET)
        assert result.verdict.verdict == "FAIL"
        assert result.verdict.confidence == 1.0
        # Should NOT have called any reviewers (early exit)
        assert len(result.reviewer_outputs) == 0

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocked_llm(self):
        """Full pipeline with mocked LLM calls produces a verdict."""
        from council.orchestrator import run_council

        # Mock all LLM calls to return PASS
        pass_response = MagicMock()
        pass_response.choices = [MagicMock()]
        pass_response.choices[0].message.content = json.dumps({
            "verdict": "PASS", "confidence": 0.8,
            "findings": [], "reasoning": "Looks good",
        })
        pass_response.usage = MagicMock(total_tokens=300)

        chair_response = MagicMock()
        chair_response.choices = [MagicMock()]
        chair_response.choices[0].message.content = json.dumps({
            "verdict": "PASS", "confidence": 0.9, "degraded": False,
            "summary": "All clear.", "accepted_blockers": [],
            "dismissed_findings": [], "all_findings": [],
            "reviewer_agreement_score": 1.0, "rationale": "Clean code.",
        })
        chair_response.usage = MagicMock(total_tokens=500)

        call_count = {"n": 0}
        async def mock_acompletion(*args, **kwargs):
            call_count["n"] += 1
            # First N calls are reviewers, last call is Chair
            if "Council Chair" in str(kwargs.get("messages", [{}])[0].get("content", "")):
                return chair_response
            return pass_response

        with patch("council.reviewers.base.litellm") as mock_reviewer_llm, \
             patch("council.chair.litellm") as mock_chair_llm:
            mock_reviewer_llm.acompletion = AsyncMock(side_effect=mock_acompletion)
            mock_chair_llm.acompletion = AsyncMock(return_value=chair_response)

            config = CouncilConfig()
            # Disable Gate Zero doc/type checks to let the diff through
            config.gate_zero.require_docs = False
            config.gate_zero.require_type_annotations = False
            config.gate_zero.require_readme_on_new_module = False
            # Add a reviewer (default CouncilConfig has empty list)
            from council.config import ReviewerConfig
            config.reviewers = [
                ReviewerConfig(
                    id="secops", name="SecOps",
                    model="anthropic/claude-sonnet-4-20250514", enabled=True,
                ),
            ]

            result = await run_council(
                diff_text=SAMPLE_DIFF,
                config=config,
            )

        assert result.verdict.verdict in ("PASS", "PASS_WITH_WARNINGS")
        assert len(result.reviewer_outputs) > 0


# ---------------------------------------------------------------------------
# Reporter Tests
# ---------------------------------------------------------------------------

class TestReporters:
    """Report generation."""

    def test_json_report(self, tmp_path):
        """JSON report writes valid JSON."""
        from council.reporters.json_report import write_json_report
        verdict = ChairVerdict(
            verdict="PASS", confidence=0.9,
            summary="Clean.", rationale="No issues.",
        )
        out = tmp_path / "report.json"
        write_json_report(verdict, out)
        data = json.loads(out.read_text())
        assert data["verdict"] == "PASS"
        assert data["confidence"] == 0.9

    def test_markdown_report(self, tmp_path):
        """Markdown report writes valid markdown."""
        from council.reporters.markdown import write_markdown_report
        verdict = ChairVerdict(
            verdict="FAIL", confidence=0.9,
            summary="Security issue found.",
            accepted_blockers=[
                ChairFinding(
                    severity="CRITICAL", category="security", file="auth.py",
                    description="SQL injection", suggestion="Fix",
                    chair_action="accepted", chair_reasoning="Evidence clear",
                )
            ],
            rationale="Confirmed vulnerability.",
        )
        out = tmp_path / "review.md"
        write_markdown_report(verdict, out)
        content = out.read_text()
        assert "FAIL" in content
        assert "SQL injection" in content
        assert "Evidence clear" in content


# ---------------------------------------------------------------------------
# Round 2 Regression Tests
# ---------------------------------------------------------------------------


class TestDeletedSymbolExtraction:
    """Verify _extract_deleted_symbols catches removed functions/classes from diff hunks."""

    def test_detects_deleted_python_function(self):
        """Removed 'def' lines are captured as deleted symbols."""
        diff_file = DiffFile(
            path="src/auth.py",
            change_type="modified",
            hunks=[DiffHunk(
                source_start=10, source_length=5,
                target_start=10, target_length=1,
                content=(
                    " import os\n"
                    "-def validate_token(token: str) -> bool:\n"
                    "-    return check(token)\n"
                    "-\n"
                    " def other_func():\n"
                ),
            )],
        )
        symbols = _extract_deleted_symbols(diff_file)
        assert len(symbols) == 1
        assert symbols[0].name == "validate_token"
        assert symbols[0].change_type == "deleted"
        assert symbols[0].kind == "function"

    def test_detects_deleted_class(self):
        """Removed 'class' lines are captured."""
        diff_file = DiffFile(
            path="src/models.py",
            change_type="modified",
            hunks=[DiffHunk(
                source_start=1, source_length=4,
                target_start=1, target_length=1,
                content=(
                    "-class AuthHandler:\n"
                    "-    pass\n"
                    " \n"
                ),
            )],
        )
        symbols = _extract_deleted_symbols(diff_file)
        assert len(symbols) == 1
        assert symbols[0].name == "AuthHandler"
        assert symbols[0].kind == "class"
        assert symbols[0].change_type == "deleted"

    def test_detects_deleted_async_function(self):
        """Removed 'async def' lines are captured."""
        diff_file = DiffFile(
            path="src/api.py",
            change_type="modified",
            hunks=[DiffHunk(
                source_start=5, source_length=3,
                target_start=5, target_length=1,
                content=(
                    "-async def handle_request(req):\n"
                    "-    return await process(req)\n"
                    " \n"
                ),
            )],
        )
        symbols = _extract_deleted_symbols(diff_file)
        assert len(symbols) == 1
        assert symbols[0].name == "handle_request"

    def test_no_false_positives_on_added_lines(self):
        """Lines starting with + should not be detected as deleted."""
        diff_file = DiffFile(
            path="src/new.py",
            change_type="modified",
            hunks=[DiffHunk(
                source_start=1, source_length=1,
                target_start=1, target_length=3,
                content=(
                    " # existing\n"
                    "+def new_function():\n"
                    "+    pass\n"
                ),
            )],
        )
        symbols = _extract_deleted_symbols(diff_file)
        assert len(symbols) == 0

    def test_no_duplicates_across_hunks(self):
        """Same symbol name removed in multiple hunks should only appear once."""
        diff_file = DiffFile(
            path="src/utils.py",
            change_type="modified",
            hunks=[
                DiffHunk(
                    source_start=1, source_length=2,
                    target_start=1, target_length=1,
                    content="-def helper():\n-    pass\n",
                ),
                DiffHunk(
                    source_start=20, source_length=2,
                    target_start=19, target_length=1,
                    content="-def helper():\n-    # overloaded\n",
                ),
            ],
        )
        symbols = _extract_deleted_symbols(diff_file)
        assert len(symbols) == 1


class TestChangedSymbolFiltering:
    """Verify _filter_to_changed_symbols only includes symbols overlapping changed hunks."""

    def test_filters_to_changed_range_only(self):
        """Only symbols whose line range overlaps a hunk are included."""
        symbols = [
            ChangedSymbol(name="untouched", kind="function", file="f.py",
                          line_start=1, line_end=10, change_type="added"),
            ChangedSymbol(name="modified_one", kind="function", file="f.py",
                          line_start=20, line_end=30, change_type="added"),
            ChangedSymbol(name="also_untouched", kind="function", file="f.py",
                          line_start=50, line_end=60, change_type="added"),
        ]
        diff_file = DiffFile(
            path="f.py", change_type="modified",
            hunks=[DiffHunk(source_start=22, source_length=5,
                            target_start=22, target_length=7, content="...")],
        )
        result = _filter_to_changed_symbols(symbols, diff_file, is_new_file=False)
        assert len(result) == 1
        assert result[0].name == "modified_one"
        assert result[0].change_type == "modified"

    def test_new_file_includes_all(self):
        """All symbols in a new file are returned as 'added'."""
        symbols = [
            ChangedSymbol(name="a", kind="function", file="new.py",
                          line_start=1, line_end=5, change_type="added"),
            ChangedSymbol(name="b", kind="class", file="new.py",
                          line_start=10, line_end=20, change_type="added"),
        ]
        diff_file = DiffFile(path="new.py", change_type="added", hunks=[])
        result = _filter_to_changed_symbols(symbols, diff_file, is_new_file=True)
        assert len(result) == 2


class TestDegradedModeUnified:
    """Verify degraded state is triggered by both exceptions AND reviewer-level errors."""

    @pytest.mark.asyncio
    async def test_malformed_findings_trigger_degraded(self):
        """Reviewer with malformed findings sets error, which orchestrator detects."""
        reviewer = SecOpsReviewer(reviewer_id="secops", model="test-model")
        malformed_response = json.dumps({
            "verdict": "FAIL",
            "confidence": 0.8,
            "findings": [
                {"severity": "HIGH", "category": "security", "file": "a.py",
                 "description": "real finding", "suggestion": "fix it"},
                {"severity": "INVALID_VALUE"},  # fails Pydantic Literal validation
                {"severity": "ALSO_BAD", "category": "fake_category"},  # also fails
            ],
            "reasoning": "test",
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = malformed_response
        mock_response.usage = MagicMock(total_tokens=100)

        review_pack = ReviewPack(
            diff_text="test", changed_files=["a.py"], added_files=[], deleted_files=[],
            changed_symbols=[], test_coverage_map={}, languages_detected=["python"],
            gate_zero_results=[], repo_policies={}, branch="main", commit_range="a..b",
            total_lines_changed=10, token_estimate=100, files_truncated=[], files_skipped=[],
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await reviewer.review(review_pack)

        # Should have parsed 1 valid finding, dropped 2 with invalid severity/category
        assert len(result.findings) == 1
        assert result.error is not None
        assert "malformed" in result.error.lower() or "1/3" in result.error

    @pytest.mark.asyncio
    async def test_degraded_reasons_propagated_to_verdict(self):
        """ChairVerdict includes specific degraded_reasons, not just a bool."""
        # Fast-path: no findings, but degraded
        verdict = await synthesize(
            review_pack=ReviewPack(
                diff_text="test", changed_files=[], added_files=[], deleted_files=[],
                changed_symbols=[], test_coverage_map={}, languages_detected=[],
                gate_zero_results=[], repo_policies={}, branch="main", commit_range="a..b",
                total_lines_changed=0, token_estimate=0, files_truncated=[], files_skipped=[],
            ),
            reviews=[
                ReviewerOutput(
                    reviewer_id="secops", model="test", verdict="PASS",
                    findings=[], confidence=0.0, reasoning="", tokens_used=0,
                    error="Parsed 1/3 findings (2 malformed/dropped)",
                ),
            ],
            degraded=True,
            degraded_reasons=["secops: Parsed 1/3 findings (2 malformed/dropped)"],
        )
        assert verdict.degraded is True
        assert len(verdict.degraded_reasons) >= 1
        assert "secops" in verdict.degraded_reasons[0]
        assert verdict.confidence < 0.95  # reduced due to degraded


class TestLinterExecution:
    """Verify linter command parsing uses shlex and supports {files} placeholder."""

    def test_shlex_split_handles_quoted_args(self):
        """Linter commands with quoted arguments are split correctly."""
        import shlex
        cmd = 'ruff check --config "pyproject.toml"'
        parts = shlex.split(cmd)
        assert parts == ["ruff", "check", "--config", "pyproject.toml"]

    def test_files_placeholder_substitution(self):
        """Commands with {files} get file paths substituted, not appended."""
        import shlex
        cmd_template = "ruff check {files} --fix"
        files = ["src/a.py", "src/b.py"]

        if "{files}" in cmd_template:
            cmd_str = cmd_template.replace("{files}", " ".join(shlex.quote(f) for f in files))
            parts = shlex.split(cmd_str)
        else:
            parts = shlex.split(cmd_template) + files

        assert parts == ["ruff", "check", "src/a.py", "src/b.py", "--fix"]

    def test_files_appended_without_placeholder(self):
        """Commands without {files} get file paths appended at the end."""
        import shlex
        cmd_template = "eslint --format json"
        files = ["src/app.ts"]

        if "{files}" in cmd_template:
            cmd_str = cmd_template.replace("{files}", " ".join(shlex.quote(f) for f in files))
            parts = shlex.split(cmd_str)
        else:
            parts = shlex.split(cmd_template) + files

        assert parts == ["eslint", "--format", "json", "src/app.ts"]


class TestRepoPolicies:
    """Verify repo_policies is populated from config, not empty."""

    def test_assemble_populates_repo_policies(self):
        """ReviewPack.repo_policies should contain actual Gate Zero config values."""
        config = CouncilConfig()
        diff_context = DiffContext(
            files=[], changed_files=[], added_files=[], deleted_files=[],
            branch="main", commit_range="a..b",
            total_additions=0, total_deletions=0,
        )

        pack = assemble(diff_context, gate_zero_findings=[], config=config)
        assert pack.repo_policies != {}
        assert "require_docs" in pack.repo_policies
        assert "require_type_annotations" in pack.repo_policies
        assert "check_secrets" in pack.repo_policies
        assert pack.repo_policies["require_docs"] is True


class TestReviewerPayloadCompleteness:
    """Verify reviewer prompt includes all ReviewPack context fields."""

    def test_payload_includes_gate_zero_results(self):
        """Gate Zero findings must appear in reviewer prompt."""
        reviewer = SecOpsReviewer(reviewer_id="secops", model="test-model")
        pack = ReviewPack(
            diff_text="+ print('hello')", changed_files=["a.py"],
            added_files=["a.py"], deleted_files=[],
            changed_symbols=[], test_coverage_map={},
            languages_detected=["python"],
            gate_zero_results=[GateZeroFinding(
                check="secret", severity="CRITICAL", category="security",
                file="config.py", line_start=3,
                message="Possible AWS key detected",
            )],
            repo_policies={"check_secrets": True},
            branch="main", commit_range="a..b",
            total_lines_changed=1, token_estimate=50,
            files_truncated=[], files_skipped=["package-lock.json"],
        )
        msg = reviewer._build_user_message(pack)
        assert "Gate Zero" in msg
        assert "Possible AWS key" in msg
        assert "package-lock.json" in msg
        assert "check_secrets" in msg

    def test_chair_payload_includes_gate_zero_and_policies(self):
        """Chair message includes Gate Zero results and repo policies."""
        pack = ReviewPack(
            diff_text="test", changed_files=["a.py"],
            added_files=[], deleted_files=[],
            changed_symbols=[], test_coverage_map={},
            languages_detected=["python"],
            gate_zero_results=[GateZeroFinding(
                check="docs", severity="HIGH", category="documentation",
                file="utils.py", line_start=10,
                message="Missing docstring on public function",
            )],
            repo_policies={"require_docs": True, "require_type_annotations": True},
            branch="main", commit_range="a..b",
            total_lines_changed=5, token_estimate=100,
            files_truncated=["big_file.py"], files_skipped=[],
        )
        msg = _build_chair_message(pack, reviews=[])
        assert "Gate Zero" in msg
        assert "Missing docstring" in msg
        assert "require_docs" in msg
        assert "big_file.py" in msg


class TestWorkflowScaffold:
    """Verify council init creates a usable GitHub workflow."""

    def test_workflow_uses_local_install(self):
        """Generated workflow must use 'pip install .' not 'pip install code-review-council'."""
        from council.cli import _DEFAULT_WORKFLOW
        assert "pip install ." in _DEFAULT_WORKFLOW
        assert "pip install code-review-council" not in _DEFAULT_WORKFLOW

    def test_workflow_passes_branch(self):
        """Generated workflow must pass --branch to avoid empty-diff reviews."""
        from council.cli import _DEFAULT_WORKFLOW
        assert "--branch" in _DEFAULT_WORKFLOW
        assert "github.base_ref" in _DEFAULT_WORKFLOW


class TestDiffTextFileBoundaries:
    """Verify assembled diff_text includes explicit file headers."""

    def test_file_headers_present(self):
        """Each file's diff should be preceded by an explicit header."""
        config = CouncilConfig()
        diff_context = DiffContext(
            files=[
                DiffFile(
                    path="src/a.py", change_type="modified",
                    hunks=[DiffHunk(
                        source_start=1, source_length=3,
                        target_start=1, target_length=3,
                        content="-old\n+new\n context\n",
                    )],
                ),
                DiffFile(
                    path="src/b.py", change_type="added",
                    hunks=[DiffHunk(
                        source_start=0, source_length=0,
                        target_start=1, target_length=2,
                        content="+line1\n+line2\n",
                    )],
                ),
            ],
            changed_files=["src/a.py", "src/b.py"],
            added_files=["src/b.py"], deleted_files=[],
            branch="main", commit_range="a..b",
            total_additions=3, total_deletions=1,
        )
        pack = assemble(diff_context, gate_zero_findings=[], config=config)
        assert "=== FILE: src/a.py (modified) ===" in pack.diff_text
        assert "=== FILE: src/b.py (added) ===" in pack.diff_text

