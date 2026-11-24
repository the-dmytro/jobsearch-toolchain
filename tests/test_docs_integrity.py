from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts/check_docs.py")
assert SPEC and SPEC.loader
check_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_docs)


class DocumentationIntegrityTests(unittest.TestCase):
    def test_public_documentation_is_consistent(self) -> None:
        self.assertEqual(check_docs.collect_issues(ROOT), [])

    def test_broken_links_and_unsupported_commands_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "README.md"
            path.write_text(
                "[missing](nope.md)\n```bash\npython -m jobtracker fetch-myboard\n```\n",
                encoding="utf-8",
            )

            issues = check_docs.check_document(path, root=root, allowed_placeholders=set())

        self.assertTrue(any("broken local link" in issue for issue in issues))
        self.assertTrue(any("nonexistent provider-specific" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
