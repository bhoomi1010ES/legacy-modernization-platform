"""Universal Test Discovery Engine (language-agnostic test asset detection)."""

from pathlib import Path
import re
from typing import List, Set
import uuid

from app.characterization.contracts.test_inventory import DiscoveredTestRecord, TestInventory


class UniversalTestDiscoveryEngine:
    """Discovers test suites, test cases, and test frameworks across any technology."""

    TEST_DIR_MARKERS: Set[str] = {"test", "tests", "spec", "specs", "testing", "fixtures"}
    TEST_FILE_PATTERNS = [
        re.compile(r"^test_.*", re.IGNORECASE),
        re.compile(r".*_test\..*", re.IGNORECASE),
        re.compile(r".*\.test\..*", re.IGNORECASE),
        re.compile(r".*\.spec\..*", re.IGNORECASE),
        re.compile(r".*_spec\..*", re.IGNORECASE),
    ]

    # Language/framework-agnostic pattern detectors
    TEST_CASE_PATTERNS = [
        re.compile(r"def\s+(test_\w+)", re.IGNORECASE),
        re.compile(r"(?:it|test)\s*\(\s*['\"]([^'\"]+)['\"]"),
        re.compile(r"func\s+(Test\w+)\s*\("),
        re.compile(r"@Test\s+(?:public\s+)?void\s+(\w+)\s*\("),
        re.compile(r"test\s+['\"]([^'\"]+)['\"]\s+do"),
    ]

    def discover(self, workspace_path: Path) -> TestInventory:
        """Scan workspace recursively for test assets without language bias."""
        records: List[DiscoveredTestRecord] = []
        frameworks: Set[str] = set()
        total_cases = 0

        if not workspace_path.exists():
            return TestInventory()

        for file_path in sorted(workspace_path.rglob("*")):
            if not file_path.is_file():
                continue

            rel_parts = file_path.relative_to(workspace_path).parts
            if any(part in {".git", "node_modules", ".venv", "dist", "build"} for part in rel_parts):
                continue

            is_test_dir = any(part.lower() in self.TEST_DIR_MARKERS for part in rel_parts[:-1])
            is_test_file = any(p.match(file_path.name) for p in self.TEST_FILE_PATTERNS)

            if not (is_test_dir or is_test_file):
                continue

            # Read and inspect test cases
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            test_names = []
            for pattern in self.TEST_CASE_PATTERNS:
                for match in pattern.finditer(content):
                    test_names.append(match.group(1))

            case_count = max(len(test_names), 1 if is_test_file else 0)
            if case_count == 0:
                continue

            # Framework detection from file signatures
            framework = "native-test-suite"
            lower_content = content.lower()
            if "pytest" in lower_content:
                framework = "pytest"
            elif "@test" in content or "junit" in lower_content:
                framework = "JUnit"
            elif any(k in content for k in ("describe(", "it(", "jest.", "vitest")):
                framework = "Jest/Vitest"
            elif "testing.t" in content:
                framework = "GoTest"

            frameworks.add(framework)
            total_cases += case_count

            rel_path = file_path.relative_to(workspace_path).as_posix()
            records.append(
                DiscoveredTestRecord(
                    test_id=f"test_{uuid.uuid4().hex[:8]}",
                    file_path=rel_path,
                    test_framework=framework,
                    test_cases_count=case_count,
                    test_names=test_names[:50],
                    confidence=0.95 if test_names else 0.80,
                )
            )

        return TestInventory(
            total_test_files=len(records),
            total_test_cases=total_cases,
            discovered_tests=records,
            frameworks_detected=sorted(list(frameworks)),
            source_paths=[r.file_path for r in records],
        )

