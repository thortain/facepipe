import unittest

from facepipe.blendshapes import IDENTIFIERS
from facepipe.frame import Frame
from facepipe.fmv3 import (
    CONTRACT_REVISION, ENC_I16, ENC_I32, HEADER_SIZE, MODE_FIXED52, MODE_VARIABLE,
    SCHEMA, SCHEMA_ACK, HELLO, FRAME, Header, Schema, build_message, decode_frame_body,
    encode_frame_body, fragment, FragmentAssembler,
)


class HeaderTests(unittest.TestCase):
    def test_header_is_40_bytes_and_round_trips(self):
        header = Header(SCHEMA, flags=0, session_id=0x1122334455667788, schema_id=1,
                        sequence=7, total_payload_length=26, part_index=0, part_count=1,
                        chunk_length=26)
        packed = header.pack()
        self.assertEqual(len(packed), HEADER_SIZE)
        self.assertEqual(packed[:4], b"FMV3")
        restored = Header.unpack(packed)
        self.assertEqual(restored.session_id, 0x1122334455667788)
        self.assertEqual(restored.total_payload_length, 26)

    def test_magic_is_checked(self):
        with self.assertRaises(ValueError):
            Header.unpack(b"XXXX" + b"\x00" * 36)


class SchemaTests(unittest.TestCase):
    def test_fixed52_schema_is_26_bytes(self):
        schema = Schema(client_nonce=1, actual_fps=60, max_udp_size=1200,
                       mode=MODE_FIXED52, blend_encoding=ENC_I32, blend_count=52)
        body = schema.body()
        self.assertEqual(len(body), 26)
        restored = Schema.from_body(body)
        self.assertTrue(restored.is_fixed52)
        self.assertEqual(restored.blend_names, IDENTIFIERS)

    def test_variable_schema_round_trip_with_unicode(self):
        names = ("jawOpen", "独自の笑顔", "myCustomSmile")
        schema = Schema(client_nonce=12345, mode=MODE_VARIABLE, blend_encoding=ENC_I16,
                        blend_count=len(names), app="FacePipe", profile="facepipe",
                        blend_names=names)
        body = schema.body()
        restored = Schema.from_body(body)
        self.assertEqual(restored.blend_names, names)
        self.assertEqual(restored.app, "FacePipe")
        self.assertEqual(restored.blend_count, 3)
        self.assertEqual(restored.blend_encoding, ENC_I16)

    def test_fixed52_rejects_extra_bytes(self):
        schema = Schema(mode=MODE_FIXED52, blend_encoding=ENC_I32, blend_count=52)
        body = schema.body() + b"\x00"
        with self.assertRaises(ValueError):
            Schema.from_body(body)


class FrameTests(unittest.TestCase):
    def test_fixed52_frame_is_256_body_bytes(self):
        schema = Schema(mode=MODE_FIXED52, blend_encoding=ENC_I32, blend_count=52,
                       blend_names=IDENTIFIERS)
        frame = Frame(blendshapes={"jawOpen": 0.5, "mouthSmileLeft": 0.25},
                      head=(1.0, 2.0, 3.0, 0.1, 0.2, 0.3),
                      right_eye=(4.0, 5.0, 6.0), left_eye=(7.0, 8.0, 9.0))
        body = encode_frame_body(frame, schema)
        self.assertEqual(len(body), 52 * 4 + 48)
        restored = decode_frame_body(body, schema)
        self.assertAlmostEqual(restored.blendshapes["jawOpen"], 0.5)
        self.assertAlmostEqual(restored.blendshapes["mouthSmileLeft"], 0.25)
        self.assertAlmostEqual(restored.head[5], 0.3, places=5)
        self.assertAlmostEqual(restored.left_eye[1], 8.0, places=5)

    def test_negative_and_over_100_values_survive(self):
        schema = Schema(mode=MODE_VARIABLE, blend_encoding=ENC_I16, blend_count=2,
                       blend_names=("jawOpen", "mouthSmileLeft"))
        frame = Frame(blendshapes={"jawOpen": -0.25, "mouthSmileLeft": 1.5})
        restored = decode_frame_body(encode_frame_body(frame, schema), schema)
        self.assertAlmostEqual(restored.blendshapes["jawOpen"], -0.25)
        self.assertAlmostEqual(restored.blendshapes["mouthSmileLeft"], 1.5)

    def test_fragmentation_reassembly(self):
        payload = bytes(range(256)) * 4
        parts = fragment(payload, 536)
        self.assertEqual(len(parts), 2)
        assembler = FragmentAssembler()
        total = len(payload)
        result = None
        for index, part in reversed(list(enumerate(parts))):  # out of order on purpose
            header = Header(SCHEMA, session_id=1, schema_id=1, total_payload_length=total,
                            part_index=index, part_count=len(parts), chunk_length=len(part))
            result = assembler.feed(header, part)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], payload)


if __name__ == "__main__":
    unittest.main()
