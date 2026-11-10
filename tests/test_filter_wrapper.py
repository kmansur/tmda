"""Regression tests for the historical tmda-filter safety wrapper.

The test harness substitutes an inert tmda-rfilter under a temporary path.
No MTA is contacted and no user's TMDA configuration is read.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "bin" / "tmda-filter"


class FilterWrapperTests(unittest.TestCase):
    def run_wrapper(self, rfilter_source):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)
            shutil.copyfile(WRAPPER, tmpdir / "tmda-filter")
            (tmpdir / "tmda-rfilter").write_text(
                rfilter_source, encoding="utf-8"
            )
            env = os.environ.copy()
            env["HOME"] = str(tmpdir)
            env["TMDARC"] = str(tmpdir / "missing-config")
            env["GLOBAL_TMDARC"] = str(tmpdir / "missing-global")
            proc = subprocess.run(
                [sys.executable, str(tmpdir / "tmda-filter")],
                input=b"Subject: test\n\nlegacy\xff\n",
                env=env,
                cwd=tmpdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            failure_path = tmpdir / "TMDA_DELIVERY_FAILURE"
            failure_contents = (
                failure_path.read_text(encoding="utf-8", errors="replace")
                if failure_path.exists() else ""
            )
            return proc, failure_contents

    def test_wrapper_preserves_success_exit_status(self):
        proc, _ = self.run_wrapper(
            "import sys\n"
            "assert sys.stdin.buffer.read().endswith(b'legacy\\xff\\n')\n"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_wrapper_preserves_filter_stop_status(self):
        proc, _ = self.run_wrapper(
            "import sys\nsys.exit(99)\n"
        )
        self.assertEqual(proc.returncode, 99, proc.stderr)

    def test_wrapper_preserves_explicit_tempfail_status(self):
        proc, _ = self.run_wrapper(
            "import sys\nsys.exit(75)\n"
        )
        self.assertEqual(proc.returncode, 75, proc.stderr)

    def test_wrapper_defers_unhandled_exception_and_logs_traceback(self):
        proc, failure_contents = self.run_wrapper(
            "raise RuntimeError('deliberate fixture failure')\n"
        )
        self.assertEqual(proc.returncode, 75, proc.stderr)
        self.assertIn("RuntimeError: deliberate fixture failure",
                      failure_contents)


if __name__ == "__main__":
    unittest.main()
