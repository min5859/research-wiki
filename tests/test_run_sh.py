import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class RunScriptTests(unittest.TestCase):
    def run_pipeline(self, dry_run: bool) -> list[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            shutil.copy2(ROOT / "run.sh", temp / "run.sh")
            (temp / ".venv/bin").mkdir(parents=True)
            (temp / "src").mkdir()
            calls = temp / "calls.log"
            python_stub = temp / ".venv/bin/python"
            python_stub.write_text(
                '#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALLS_FILE"\n',
                encoding="utf-8",
            )
            python_stub.chmod(0o755)

            env = dict(os.environ)
            env.update({
                "HOME": str(temp),
                "CALLS_FILE": str(calls),
                "RESEARCH_WIKI_DRY_RUN": "1" if dry_run else "0",
            })
            result = subprocess.run(
                ["/bin/bash", str(temp / "run.sh")],
                cwd=temp,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return calls.read_text(encoding="utf-8").splitlines()

    def test_normal_publish_has_no_empty_argument_failure(self):
        calls = self.run_pipeline(dry_run=False)
        self.assertTrue(calls[-1].endswith("src/publish.py"), calls[-1])

    def test_dry_run_passes_explicit_flag(self):
        calls = self.run_pipeline(dry_run=True)
        self.assertTrue(calls[-1].endswith("src/publish.py --dry-run"), calls[-1])


if __name__ == "__main__":
    unittest.main()
