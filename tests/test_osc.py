import struct
import unittest

from facepipe.osc import bundle, bundle_packets, osc_message


class OscWireTests(unittest.TestCase):
    def test_message_has_padded_address_and_type_tag(self):
        self.assertEqual(osc_message("/a", 1.0),
                         b"/a\x00\x00,f\x00\x00" + struct.pack(">f", 1.0))

    def test_bundle_has_immediate_timetag_and_element_size(self):
        message = osc_message("/VMC/Ext/Blend/Val", "jawOpen", 0.5)
        packet = bundle([("/VMC/Ext/Blend/Val", ("jawOpen", 0.5))])
        self.assertEqual(packet[:16], b"#bundle\x00" + struct.pack(">Q", 1))
        self.assertEqual(struct.unpack(">I", packet[16:20])[0], len(message))
        self.assertEqual(packet[20:], message)

    def test_vmc_messages_stay_below_one_udp_packet_limit(self):
        messages = [("/VMC/Ext/Blend/Val", (f"shape{index}", 0.5))
                    for index in range(52)]
        messages.append(("/VMC/Ext/Blend/Apply", ()))
        packets = list(bundle_packets(messages, max_size=1400))
        self.assertGreater(len(packets), 1)
        self.assertTrue(all(len(packet) <= 1400 for packet in packets))
        self.assertIn(b"/VMC/Ext/Blend/Apply", packets[-1])


if __name__ == "__main__":
    unittest.main()
