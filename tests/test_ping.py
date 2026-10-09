import unittest
from unittest.mock import patch, MagicMock
from ping_rtt.ping import ping
class TestPing(unittest.TestCase):
    @patch("ping_rtt.ping.subprocess.run")
    def test_successful_ping(self, mock_run):
        """Test ping when the target responds successfully."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "Reply from 8.8.8.8: time=20ms\n"
                "Reply from 8.8.8.8: time=25ms\n"
                "Reply from 8.8.8.8: time=30ms\n"
                "Reply from 8.8.8.8: time=22ms\n"
            ),
            stderr=""
        )
        result = ping("8.8.8.8", count=4)
        self.assertEqual(result["target"], "8.8.8.8")
        self.assertEqual(result["sent"], 4)
        self.assertEqual(result["received"], 4)
        self.assertEqual(result["packet_loss"], 0)
        self.assertEqual(result["latency_ms"], [20, 25, 30, 22])
        self.assertEqual(result["min_rtt"], 20)
        self.assertEqual(result["max_rtt"], 30)
        self.assertAlmostEqual(result["avg_rtt"], 24.25)
    @patch("ping_rtt.ping.subprocess.run")
    def test_partial_packet_loss(self, mock_run):
        """Test ping when some packets are lost."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "Reply from 8.8.8.8: time=20ms\n"
                "Reply from 8.8.8.8: time=30ms\n"
                "Packets: Sent = 4, Received = 2, Lost = 2 (50% loss)\n"
            ),
            stderr=""
        )
        result = ping("8.8.8.8", count=4)
        self.assertEqual(result["sent"], 4)
        self.assertEqual(result["received"], 2)
        self.assertEqual(result["packet_loss"], 50)
        self.assertEqual(result["latency_ms"], [20, 30])
    @patch("ping_rtt.ping.subprocess.run")
    def test_no_responses(self, mock_run):
        """Test ping when no replies are received."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="Request timed out.\n" * 4,
            stderr=""
        )
        result = ping("192.0.2.1", count=4)
        self.assertEqual(result["target"], "192.0.2.1")
        self.assertEqual(result["sent"], 4)
        self.assertEqual(result["received"], 0)
        self.assertEqual(result["packet_loss"], 100)
        self.assertEqual(result["latency_ms"], [])
    @patch("ping_rtt.ping.subprocess.run")
    def test_subprocess_timeout(self, mock_run):
        """Test handling of a subprocess timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="ping",
            timeout=30
        )
        result = ping("8.8.8.8", count=4)
        self.assertIn("error", result)
        self.assertIsNotNone(result["error"])
    @patch("ping_rtt.ping.subprocess.run")
    def test_general_exception(self, mock_run):
        """Test handling of an unexpected error."""
        mock_run.side_effect = OSError("Ping command not found")
        result = ping("example.com", count=4)
        self.assertIn("error", result)
        self.assertIn("Ping command not found", result["error"])
if __name__ == "__main__":
    unittest.main()