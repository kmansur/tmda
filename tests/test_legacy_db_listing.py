"""Keep Python 2 byte-for-byte output from the legacy CDB/DBM tools."""
import dbm
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRIB = ROOT / "contrib"


class BinaryDatabaseListingTests(unittest.TestCase):
    def test_printdbm_preserves_high_bit_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "legacy.db")
            with dbm.open(database_path, "c") as database:
                database[b"ALICE@EX\xc9MPLE.ORG"] = b"accept\xff"
            result = subprocess.run(
                [sys.executable, str(CONTRIB / "printdbm"), database_path],
                capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout, b"ALICE@EX\xc9MPLE.ORG accept\xff\n"
            )

    def test_printcdb_preserves_original_bytes_from_legacy_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / "cdb.py"
            stub.write_text(
                "def init(path):\n"
                "    return {b'ALICE@EX\\xc9MPLE.ORG': b'accept\\xff'}\n",
                encoding="ascii",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = directory + os.pathsep + env.get("PYTHONPATH", "")
            result = subprocess.run(
                [sys.executable, str(CONTRIB / "printcdb"),
                 str(Path(directory) / "old.cdb")],
                env=env, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout, b"ALICE@EX\xc9MPLE.ORG accept\xff\n"
            )


if __name__ == "__main__":
    unittest.main()
