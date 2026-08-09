from __future__ import annotations

import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from jobtracker.automation import run_doctor, run_pipeline, scaffold_config

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "jobtracker/fixtures/provider_fetch"


class FreshCloneAcceptanceTests(unittest.TestCase):
    def test_neutral_scaffold_runs_idempotently_in_local_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            shutil.copyfile(ROOT / "config/jobsearch.example.toml", root / "config/jobsearch.example.toml")
            shutil.copytree(ROOT / "profile/templates", root / "profile/templates")
            scaffold_config(root=root)
            for name in ("cv.md", "preferences.md", "project_evidence.md", "writing_style.md"):
                (root / "profile" / name).write_text(
                    f"# {name}\nFictitious acceptance content.\n", encoding="utf-8"
                )

            doctor = run_doctor(root=root, skip_network=True)
            self.assertEqual(doctor["status"], "ready", doctor["issues"])

            now = datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc)
            first = run_pipeline("jobboards", root=root, fixture_dir=FIXTURES, now=now)
            second = run_pipeline("jobboards", root=root, fixture_dir=FIXTURES, now=now)

            self.assertEqual(first["stored"][0]["run_key"], second["stored"][0]["run_key"])
            with closing(sqlite3.connect(root / "outputs/jobsearch.sqlite3")) as conn:
                run_count = conn.execute("select count(*) from automation_runs").fetchone()[0]
                opportunity_count = conn.execute("select count(*) from opportunities").fetchone()[0]
            self.assertEqual(run_count, 1)
            self.assertEqual(opportunity_count, first["stored"][0]["opportunities"])

    def test_private_runtime_paths_are_gitignored(self) -> None:
        paths = [
            "config/jobsearch.toml",
            "profile/cv.md",
            "outputs/jobsearch.sqlite3",
            ".env",
            ".jobsearch-onboarding.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                result = subprocess.run(["git", "check-ignore", "--quiet", path], cwd=ROOT, check=False)
                self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
