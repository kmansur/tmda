"""Exercise tmda-pending with a historical non-UTF-8 virtual home path."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PENDING = ROOT / "bin" / "tmda-pending"


@unittest.skipUnless(os.name == "posix", "requires byte-preserving POSIX paths")
class VirtualHomePathTests(unittest.TestCase):
    def test_pending_uses_undecodable_virtual_home_from_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_home = os.fsencode(tmp) + b"/legacy-\xff"
            os.mkdir(raw_home)
            home = pathlib.Path(os.fsdecode(raw_home))
            tmda = home / ".tmda"
            tmda.mkdir()
            (tmda / "pending").mkdir()
            key = tmda / "crypt_key"
            key.write_text("00112233445566778899aabbccddeeff00112233",
                           encoding="ascii")
            key.chmod(0o600)
            (tmda / "config").write_text(
                "USERNAME = 'alice'\nHOSTNAME = 'example.org'\n",
                encoding="ascii",
            )
            helper = pathlib.Path(tmp) / "vhome"
            helper.write_text(
                "#!" + sys.executable + "\n"
                "import os\n"
                "os.write(1, " + repr(raw_home + b"\n") + ")\n",
                encoding="ascii",
            )
            helper.chmod(0o700)
            env = os.environ.copy()
            env["HOME"] = tmp
            env["GLOBAL_TMDARC"] = str(pathlib.Path(tmp) / "missing-global")
            env.pop("TMDARC", None)
            result = subprocess.run(
                [sys.executable, str(PENDING),
                 "--vhome-script=" + str(helper),
                 "--vhome-user=alice", "--vhome-domain=example.org",
                 "-b", "-T"],
                cwd=ROOT, env=env, capture_output=True, timeout=15,
            )
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )


if __name__ == "__main__":
    unittest.main()
