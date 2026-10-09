

import unittest

from dns.dns_lookup import _result, describe_record_used, resolve


class TestDNSLookup(unittest.TestCase):
    def test_localhost(self):
        r = resolve("localhost")
        self.assertTrue(r["success"])
        self.assertEqual(r["ip"], "127.0.0.1")
        self.assertEqual(r["ip_version"], 4)

    def test_hostname_has_a_record(self):
        r = resolve("google.com")
        self.assertTrue(r["success"])
        self.assertEqual(r["ip_version"], 4)
        self.assertIn("A", [rec["type"] for rec in r["records"]])
        self.assertTrue(r["ipv4"])
        self.assertIn(r["record_used"], ("A", "CNAME"))

    def test_record_fields(self):
        r = resolve("google.com")
        for rec in r["records"]:
            self.assertEqual(set(rec), {"type", "name", "value", "ttl"})

    def test_mx_record_for_mail_domain(self):
        r = resolve("gmail.com")
        self.assertIn("MX", [rec["type"] for rec in r["records"]])

    def test_ipv4_input(self):
        r = resolve("8.8.8.8")
        self.assertTrue(r["success"])
        self.assertEqual(r["ip"], "8.8.8.8")
        self.assertEqual(r["ip_version"], 4)

    def test_ipv6_input(self):
        r = resolve("2001:4860:4860::8888")
        self.assertTrue(r["success"])
        self.assertEqual(r["ip_version"], 6)

    def test_invalid_hostname(self):
        r = resolve("this-does-not-exist.invalid")
        self.assertFalse(r["success"])
        self.assertIsNone(r["ip"])
        self.assertIsNone(r["record_used"])
        self.assertEqual(r["status"], "FAILED")
        self.assertIsNotNone(r["error"])

    def test_empty_input(self):
        self.assertFalse(resolve("   ")["success"])

    def test_spaces_in_input(self):
        self.assertFalse(resolve("exa mple.com")["success"])

    def test_none_input(self):
        self.assertFalse(resolve(None)["success"])

    def test_record_used_cname(self):
        records = [
            {"type": "CNAME", "name": "mail.example.com", "value": "real.example.net", "ttl": 60},
            {"type": "A", "name": "real.example.net", "value": "192.0.2.10", "ttl": 60},
        ]
        r = _result("mail.example.com", ip="192.0.2.10", hostname="mail.example.com", records=records)
        self.assertEqual(r["record_used"], "CNAME")
        self.assertEqual(r["cname_chain"], [("mail.example.com", "real.example.net")])
        text = "\n".join(describe_record_used(r))
        self.assertIn("CNAME", text)
        self.assertIn("real.example.net", text)

    def test_record_used_direct_a(self):
        records = [{"type": "A", "name": "example.com", "value": "192.0.2.10", "ttl": 60}]
        r = _result("example.com", ip="192.0.2.10", hostname="example.com", records=records)
        self.assertEqual(r["record_used"], "A")
        self.assertEqual(r["cname_chain"], [])


if __name__ == "__main__":
    unittest.main()
