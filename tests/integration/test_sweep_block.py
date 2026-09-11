"""The sweep block, run on loopback: every 127.x address answers ping, so only the addresses with a
listener bound to a test port may come out as candidates, and only their subnets may reach CCT."""
import tempfile
import unittest
from pathlib import Path

from .support import Listener, run_block


class SweepBlockTest(unittest.TestCase):
    def test_only_addresses_with_a_web_port_become_candidates(self):
        with tempfile.TemporaryDirectory() as tmp, Listener("127.0.1.5", 18099), Listener("127.0.0.9", 18098):
            result = run_block("SWEEP", {"STARTIP": "127.0.0.1", "ENDIP": "127.0.2.255", "HTTPPORT": "18099",
                                         "HTTPSPORT": "18098", "PSOUT": tmp, "LOCALAPPDATA": tmp})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "767|2|2", result.stderr)

            stage = Path(tmp)
            self.assertEqual((stage / "runlist.txt").read_text().split("\n")[:2],
                             ["127.0.0.1 127.0.0.255", "127.0.1.0 127.0.1.255"])
            sweep = [ln for ln in (stage / "sweep.txt").read_text().splitlines() if ln]
            self.assertEqual(sweep, ["127.0.0.1 127.0.0.255 255 1",
                                     "127.0.1.0 127.0.1.255 256 1",
                                     "127.0.2.0 127.0.2.255 256 0"])
            self.assertEqual([ln for ln in (stage / "candidates.txt").read_text().splitlines() if ln],
                             ["127.0.0.9", "127.0.1.5"])
            self.assertTrue((stage / "logmark.txt").exists())
            self.assertIn("767 of 767 addresses checked, 767 answered", result.stderr)

    def test_a_range_with_nothing_answering_yields_no_subnets(self):
        # 0.0.0.x is not a destination Windows will send to, so every ping fails at once.
        with tempfile.TemporaryDirectory() as tmp:
            result = run_block("SWEEP", {"STARTIP": "0.0.0.1", "ENDIP": "0.0.0.20", "HTTPPORT": "80",
                                         "HTTPSPORT": "443", "PSOUT": tmp, "LOCALAPPDATA": tmp})
            self.assertEqual(result.stdout.strip(), "0|0|0", result.stderr)
            self.assertEqual((Path(tmp) / "runlist.txt").read_text().strip(), "")

    def test_a_single_address_range_is_one_subnet(self):
        with tempfile.TemporaryDirectory() as tmp, Listener("127.0.0.1", 18097):
            result = run_block("SWEEP", {"STARTIP": "127.0.0.1", "ENDIP": "127.0.0.1", "HTTPPORT": "18097",
                                         "HTTPSPORT": "18097", "PSOUT": tmp, "LOCALAPPDATA": tmp})
            self.assertEqual(result.stdout.strip(), "1|1|1", result.stderr)
            self.assertEqual((Path(tmp) / "runlist.txt").read_text().strip(), "127.0.0.1 127.0.0.1")


if __name__ == "__main__":
    unittest.main()
