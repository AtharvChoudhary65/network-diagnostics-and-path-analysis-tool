"""
Unit tests for traceroute/traceroute.py.

These tests do not touch the network: the traceroute command is mocked and
parsing is checked against captured sample outputs from each OS.

Run from the project root:
    python -m unittest discover -s tests -v
or run this file directly (e.g. VS Code "Run Python File").
"""

import os
import subprocess
import sys
import unittest
from unittest import mock


def _add_repo_root_to_path() -> None:
    """Make ``import traceroute`` find the package, however this file is run.

    When a file is run directly, Python puts the file's own folder first on
    sys.path. If that folder is ``traceroute/``, ``import traceroute`` would
    load ``traceroute/traceroute.py`` instead of the package. Putting the repo
    root first avoids that.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isfile(os.path.join(root, "traceroute", "traceroute.py")):
        parent = os.path.dirname(root)
        if parent == root:  # reached the drive root without finding the repo
            return
        root = parent
    # Drop the traceroute/ folder itself from sys.path so it can't shadow the package.
    package_dir = os.path.normcase(os.path.join(root, "traceroute"))
    sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or ".")) != package_dir]
    sys.path.insert(0, root)


_add_repo_root_to_path()

from traceroute import traceroute as tr  # noqa: E402  (import after path setup)

LINUX_OUTPUT = """\
traceroute to example.com (93.184.216.34), 30 hops max, 60 byte packets
 1  192.168.1.1  1.234 ms  1.100 ms  1.050 ms
 2  * * *
 3  10.0.0.1  5.123 ms *  5.200 ms
 4  72.14.215.85  12.001 ms 72.14.215.86  13.500 ms  12.900 ms
 5  93.184.216.34  20.4 ms  20.1 ms  19.9 ms
"""

MACOS_OUTPUT = """\
traceroute to 8.8.8.8 (8.8.8.8), 64 hops max, 52 byte packets
 1  192.168.0.1  3.512 ms  2.901 ms  2.774 ms
 2  100.64.0.1  9.832 ms  8.997 ms  9.120 ms
 3  * * *
 4  8.8.8.8  14.551 ms  14.210 ms  13.987 ms
"""

WINDOWS_OUTPUT = """\

Tracing route to example.com [93.184.216.34]
over a maximum of 30 hops:

  1    <1 ms    <1 ms    <1 ms  192.168.1.1
  2     *        *        *     Request timed out.
  3    10 ms     9 ms    11 ms  10.0.0.1
  4    25 ms    24 ms    26 ms  93.184.216.34

Trace complete.
"""

IPV6_OUTPUT = """\
traceroute to 2001:4860:4860::8888 (2001:4860:4860::8888), 30 hops max, 80 byte packets
 1  fe80::1  1.500 ms  1.400 ms  1.300 ms
 2  2001:4860:4860::8888  12.0 ms  11.5 ms  11.8 ms
"""

UNREACHABLE_ANNOTATION_OUTPUT = """\
traceroute to 10.255.255.1 (10.255.255.1), 30 hops max, 60 byte packets
 1  192.168.1.1  1.0 ms !H  1.1 ms !H  1.2 ms !H
"""


class TestParsing(unittest.TestCase):
    def test_linux_output(self):
        hops = tr.parse_traceroute_output(LINUX_OUTPUT)
        self.assertEqual([h.hop_number for h in hops], [1, 2, 3, 4, 5])

        self.assertEqual(hops[0].ip_address, "192.168.1.1")
        self.assertEqual(hops[0].rtts_ms, [1.234, 1.100, 1.050])
        self.assertTrue(hops[0].responded)

    def test_non_responding_hop(self):
        hop = tr.parse_traceroute_output(LINUX_OUTPUT)[1]
        self.assertIsNone(hop.ip_address)
        self.assertEqual(hop.rtts_ms, [None, None, None])
        self.assertFalse(hop.responded)
        self.assertIsNone(hop.avg_rtt_ms)

    def test_partial_timeout_ignored_in_average(self):
        hop = tr.parse_traceroute_output(LINUX_OUTPUT)[2]
        self.assertEqual(hop.rtts_ms, [5.123, None, 5.200])
        self.assertAlmostEqual(hop.avg_rtt_ms, 5.162, places=3)
        self.assertEqual(hop.min_rtt_ms, 5.123)
        self.assertEqual(hop.max_rtt_ms, 5.200)

    def test_multiple_addresses_per_hop(self):
        hop = tr.parse_traceroute_output(LINUX_OUTPUT)[3]
        self.assertEqual(hop.addresses, ["72.14.215.85", "72.14.215.86"])
        self.assertEqual(hop.ip_address, "72.14.215.85")
        self.assertEqual(len(hop.rtts_ms), 3)

    def test_macos_output(self):
        hops = tr.parse_traceroute_output(MACOS_OUTPUT)
        self.assertEqual(len(hops), 4)
        self.assertFalse(hops[2].responded)
        self.assertEqual(hops[3].ip_address, "8.8.8.8")

    def test_windows_output(self):
        hops = tr.parse_traceroute_output(WINDOWS_OUTPUT)
        self.assertEqual(len(hops), 4)
        self.assertEqual(hops[0].ip_address, "192.168.1.1")
        self.assertEqual(hops[0].rtts_ms, [tr.LESS_THAN_ONE_MS_VALUE] * 3)
        self.assertFalse(hops[1].responded)
        self.assertEqual(hops[2].rtts_ms, [10.0, 9.0, 11.0])

    def test_ipv6_output(self):
        hops = tr.parse_traceroute_output(IPV6_OUTPUT)
        self.assertEqual(hops[0].ip_address, "fe80::1")
        self.assertEqual(hops[1].ip_address, "2001:4860:4860::8888")
        self.assertEqual(hops[1].rtts_ms, [12.0, 11.5, 11.8])

    def test_annotations_are_ignored(self):
        hop = tr.parse_traceroute_output(UNREACHABLE_ANNOTATION_OUTPUT)[0]
        self.assertEqual(hop.rtts_ms, [1.0, 1.1, 1.2])

    def test_empty_output(self):
        self.assertEqual(tr.parse_traceroute_output(""), [])

    def test_hop_to_dict(self):
        data = tr.parse_traceroute_output(LINUX_OUTPUT)[0].to_dict()
        self.assertEqual(data["hop"], 1)
        self.assertEqual(data["ip"], "192.168.1.1")
        self.assertTrue(data["responded"])
        self.assertIn("avg_rtt_ms", data)


class TestValidation(unittest.TestCase):
    def test_valid_targets(self):
        for target in ["example.com", "8.8.8.8", "2001:db8::1", "my-host.local"]:
            self.assertEqual(tr.validate_target(f"  {target} "), target)

    def test_invalid_targets(self):
        for target in ["", "   ", "-n", "example.com; rm -rf /", "a b", "x" * 300]:
            with self.assertRaises(ValueError):
                tr.validate_target(target)

    def test_invalid_options(self):
        with self.assertRaises(ValueError):
            tr.run_traceroute("example.com", max_hops=0)
        with self.assertRaises(ValueError):
            tr.run_traceroute("example.com", timeout=0)
        with self.assertRaises(ValueError):
            tr.run_traceroute("example.com", queries=50)


class TestBuildCommand(unittest.TestCase):
    def test_linux_command(self):
        cmd = tr.build_command("8.8.8.8", 20, 2, 3, system_name="Linux")
        self.assertEqual(
            cmd, ["traceroute", "-n", "-m", "20", "-q", "3", "-w", "2", "8.8.8.8"]
        )

    def test_macos_command(self):
        cmd = tr.build_command("8.8.8.8", 20, 1.5, 2, system_name="Darwin")
        self.assertEqual(cmd[0], "traceroute")
        self.assertIn("1.5", cmd)

    def test_windows_command(self):
        cmd = tr.build_command("8.8.8.8", 20, 2, 3, system_name="Windows")
        self.assertEqual(cmd, ["tracert", "-d", "-h", "20", "-w", "2000", "8.8.8.8"])


class TestRunTraceroute(unittest.TestCase):
    def _completed(self, stdout, returncode=0, stderr=""):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )

    @mock.patch("traceroute.traceroute.platform.system", return_value="Linux")
    @mock.patch("traceroute.traceroute.subprocess.run")
    def test_successful_run(self, mock_run, _mock_system):
        mock_run.return_value = self._completed(LINUX_OUTPUT)
        result = tr.run_traceroute("example.com")

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.hops), 5)
        self.assertEqual(result.destination_ip, "93.184.216.34")
        self.assertTrue(result.reached_destination)

        # Must never go through a shell.
        _, kwargs = mock_run.call_args
        self.assertNotIn("shell", kwargs)

    @mock.patch("traceroute.traceroute.platform.system", return_value="Windows")
    @mock.patch("traceroute.traceroute.subprocess.run")
    def test_windows_run(self, mock_run, _mock_system):
        mock_run.return_value = self._completed(WINDOWS_OUTPUT)
        result = tr.run_traceroute("example.com")
        self.assertEqual(mock_run.call_args[0][0][0], "tracert")
        self.assertTrue(result.reached_destination)

    @mock.patch("traceroute.traceroute.subprocess.run")
    def test_destination_not_reached(self, mock_run):
        mock_run.return_value = self._completed(MACOS_OUTPUT.replace(" 4  8.8.8.8", " 4  9.9.9.9"))
        result = tr.run_traceroute("8.8.8.8")
        self.assertTrue(result.success)
        self.assertFalse(result.reached_destination)

    @mock.patch("traceroute.traceroute.subprocess.run", side_effect=FileNotFoundError)
    def test_tool_not_installed(self, _mock_run):
        result = tr.run_traceroute("example.com")
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    @mock.patch("traceroute.traceroute.subprocess.run")
    def test_overall_timeout_keeps_partial_hops(self, mock_run):
        partial = "\n".join(LINUX_OUTPUT.splitlines()[:3]).encode()
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="traceroute", timeout=1, output=partial)
        result = tr.run_traceroute("example.com")
        self.assertTrue(result.success)
        self.assertEqual(len(result.hops), 2)
        self.assertIn("did not finish", result.error)

    @mock.patch("traceroute.traceroute.subprocess.run")
    def test_unknown_host(self, mock_run):
        mock_run.return_value = self._completed(
            "", returncode=2, stderr="nosuchhost.invalid: Name or service not known"
        )
        result = tr.run_traceroute("nosuchhost.invalid")
        self.assertFalse(result.success)
        self.assertIn("not known", result.error)

    @mock.patch("traceroute.traceroute.subprocess.run")
    def test_invalid_target_does_not_run_command(self, mock_run):
        result = tr.run_traceroute("-rf")
        self.assertFalse(result.success)
        mock_run.assert_not_called()

    def test_result_to_dict_is_json_serialisable(self):
        import json

        result = tr.TracerouteResult(
            target="x", success=True, hops=tr.parse_traceroute_output(LINUX_OUTPUT)
        )
        json.dumps(result.to_dict())


class TestFormatting(unittest.TestCase):
    def test_table_contains_hops(self):
        result = tr.TracerouteResult(
            target="example.com",
            success=True,
            hops=tr.parse_traceroute_output(LINUX_OUTPUT),
            destination_ip="93.184.216.34",
            reached_destination=True,
        )
        text = tr.format_result(result)
        self.assertIn("192.168.1.1", text)
        self.assertIn("no response", text)
        self.assertIn("(+1 more)", text)
        self.assertIn("reached", text)

    def test_failure_message(self):
        result = tr.TracerouteResult(target="x", success=False, error="boom")
        self.assertEqual(tr.format_result(result), "Traceroute failed: boom")


if __name__ == "__main__":
    unittest.main()
