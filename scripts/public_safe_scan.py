from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCAN_TARGETS = ["README.md", "docs", "apps", "scripts", "tests", "data"]
SKIP_PARTS = {".git", ".pytest_cache", "__pycache__", ".venv", "htmlcov", "runtime"}
SCAN_SUFFIXES = {".md", ".py", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".txt"}


@dataclass(frozen=True)
class ScanRule:
    rule_id: str
    pattern: re.Pattern[str]
    category: str


RULES = [
    ScanRule(
        "live_auth_material",
        re.compile(
            r"(?i)(sk_live_[A-Za-z0-9]+|sk-proj-[A-Za-z0-9_-]+|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})"
        ),
        "auth_material",
    ),
    ScanRule(
        "auth_assignment",
        re.compile(r"(?i)\b(api[_-]?key|password|token|secret)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
        "auth_material",
    ),
    ScanRule("api_key_header_reference", re.compile(r"X-API-Key"), "header_reference"),
    ScanRule("webhook_signature_header_reference", re.compile(r"X-Webhook-Signature"), "header_reference"),
    ScanRule("synthetic_fixture_value", re.compile(r"test-webhook-secret|sandbox-key-[ab]"), "synthetic_fixture"),
    ScanRule("unsafe_boundary_phrase", re.compile(r"callback URL|real endpoint|raw credential", re.IGNORECASE), "boundary_wording"),
    ScanRule(
        "external_network_target",
        re.compile(r"https?://(?!(127\.0\.0\.1|localhost|github\.com|img\.shields\.io|skills\.sh))\S+"),
        "network_target",
    ),
    ScanRule("named_partner_claim", re.compile(r"\b(AIS|TRUE)\b"), "partner_claim"),
]


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_files(root: Path, targets: Iterable[str]) -> Iterable[Path]:
    for target in targets:
        path = root / target
        if path.is_file() and path.suffix in SCAN_SUFFIXES:
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix in SCAN_SUFFIXES and not any(part in SKIP_PARTS for part in child.parts):
                    yield child


def _is_allowed_reference(path: Path, root: Path, rule: ScanRule) -> bool:
    rel = _relative(path, root)
    if rel == "scripts/public_safe_scan.py":
        return True
    if rule.rule_id in {"api_key_header_reference", "webhook_signature_header_reference"}:
        return rel == "README.md" or rel.startswith(("docs/", "apps/api/", "tests/")) or rel == "scripts/run_partner_sandbox_flow.py"
    if rule.rule_id == "synthetic_fixture_value":
        return rel.startswith("tests/") or rel in {
            "scripts/run_partner_sandbox_flow.py",
            "tests/test_partner_sandbox_flow.py",
            "tests/test_pilot_report.py",
        }
    if rule.rule_id == "unsafe_boundary_phrase":
        return rel == "README.md" or rel.startswith(("docs/", "scripts/", "tests/"))
    return False


def scan_public_safe(root: Path = ROOT, targets: Iterable[str] = SCAN_TARGETS) -> dict[str, Any]:
    files = sorted(set(_iter_files(root, targets)))
    issues: list[dict[str, Any]] = []
    allowed_references = 0

    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for rule in RULES:
                if not rule.pattern.search(line):
                    continue
                if _is_allowed_reference(path, root, rule):
                    allowed_references += 1
                    continue
                issues.append(
                    {
                        "file": _relative(path, root),
                        "line": line_number,
                        "rule_id": rule.rule_id,
                        "category": rule.category,
                    }
                )

    return {
        "report_type": "public-safe-scan",
        "data_boundary": "synthetic-public-safe",
        "status": "passed" if not issues else "needs_review",
        "scanned_files": len(files),
        "allowed_references": allowed_references,
        "issues": issues,
    }


def render_markdown(report: dict[str, Any]) -> str:
    issue_lines = "\n".join(
        f"- {issue['file']}:{issue['line']} `{issue['rule_id']}`" for issue in report["issues"]
    )
    if not issue_lines:
        issue_lines = "- No issues found."
    return f"""# Public-Safe Scan

Data boundary: `{report['data_boundary']}`
Status: `{report['status']}`

## Summary

- Scanned files: `{report['scanned_files']}`
- Allowed references: `{report['allowed_references']}`
- Issues: `{len(report['issues'])}`

## Issues

{issue_lines}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan repo text for public-safe release issues.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    report = scan_public_safe()
    rendered = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2)
    print(rendered)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
