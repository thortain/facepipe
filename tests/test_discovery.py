import unittest

from facepipe.discovery import DiscoveryServer, discover
from facepipe.fmv3 import FMV3Sender


class DiscoveryTests(unittest.TestCase):
    def test_local_service_is_discoverable(self):
        server = DiscoveryServer("127.0.0.1", port=51120, udp_port=51121)
        server.start()
        try:
            found = discover(host="127.0.0.1", port=51120, timeout=0.4)
        finally:
            server.close()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["fmv3_udp"], 51121)

    def test_public_bind_is_rejected(self):
        with self.assertRaises(ValueError):
            FMV3Sender(bind_host="8.8.8.8")


if __name__ == "__main__":
    unittest.main()
