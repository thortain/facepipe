import unittest

from facepipe.blendshapes import IDENTIFIERS, RAW_VALUES, normalize_name
from facepipe.frame import Frame
from facepipe.text_protocol import decode, encode, official_sample


class TextProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        frame = Frame(
            blendshapes={"jawOpen": 0.42, "mouthSmile_L": 0.8, "eyeBlink_R": 0.15},
            head=(1.0, 2.0, 3.0, 0.1, 0.2, 0.3),
            right_eye=(4.0, 5.0, 6.0),
            left_eye=(7.0, 8.0, 9.0),
        )
        text = encode(frame)
        parsed = decode(text)
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed.blendshapes["jawOpen"], 0.42, places=3)
        self.assertAlmostEqual(parsed.blendshapes["mouthSmileLeft"], 0.8, places=3)
        self.assertAlmostEqual(parsed.head[0], 1.0, places=5)
        self.assertAlmostEqual(parsed.left_eye[2], 9.0, places=5)

    def test_official_sample_parses(self):
        frame = decode(official_sample())
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame.blendshapes), 52)
        self.assertAlmostEqual(frame.blendshapes["jawOpen"], 0.12)
        self.assertAlmostEqual(frame.blendshapes["mouthShrugUpper"], 0.26)
        self.assertAlmostEqual(frame.head[0], -21.488958, places=6)
        self.assertAlmostEqual(frame.right_eye[0], 6.0297494, places=6)

    def test_v2_negative_values(self):
        frame = Frame(blendshapes={"mouthSmile_L": -0.25})
        text = encode(frame, version=2)
        self.assertIn("mouthSmile_L&-25", text)
        parsed = decode(text)
        self.assertAlmostEqual(parsed.blendshapes["mouthSmileLeft"], -0.25)

    def test_raw_wire_names_read_identifier_values(self):
        frame = Frame(blendshapes={"eyeBlinkLeft": 0.67, "mouthSmileRight": 0.42})
        wire = encode(frame, version=2, names=RAW_VALUES)
        self.assertIn("eyeBlink_L&67|", wire)
        self.assertIn("mouthSmile_R&42|", wire)

    def test_decoded_wire_names_are_usable_by_fmv3(self):
        frame = decode("eyeBlink_L&67|mouthSmile_R&42|head#0,0,0,0,0,0|")
        self.assertEqual(frame.blendshapes["eyeBlinkLeft"], 0.67)
        self.assertEqual(frame.blendshapes["mouthSmileRight"], 0.42)

    def test_stray_tokens_are_ignored(self):
        frame = decode("jawOpen-50|1|?eyeBlink_L-20|=head#1,2,3,4,5,6|")
        self.assertEqual(len(frame.blendshapes), 2)
        self.assertAlmostEqual(frame.head[5], 6.0)


class BlendshapeTests(unittest.TestCase):
    def test_name_normalisation(self):
        self.assertEqual(normalize_name("eyeBlink_L"), "eyeBlinkLeft")
        self.assertEqual(normalize_name("eyeBlinkLeft"), "eyeBlinkLeft")
        self.assertEqual(normalize_name("jawOpen"), "jawOpen")
        self.assertEqual(normalize_name("EYEBLINK_L"), "eyeBlinkLeft")

    def test_tables_are_consistent(self):
        self.assertEqual(len(IDENTIFIERS), 52)
        self.assertEqual(len(RAW_VALUES), 52)
        self.assertEqual(sorted(IDENTIFIERS), list(IDENTIFIERS))


if __name__ == "__main__":
    unittest.main()
