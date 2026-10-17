import threading
import unittest

from facepipe.blendshapes import IDENTIFIERS
from facepipe.capture import synthetic_frames
from facepipe.fmv3 import FMV3Receiver, FMV3Sender, MODE_FIXED52, MODE_VARIABLE

IOS_PORT = 51083
PC_PORT = 51084


class LoopbackTests(unittest.TestCase):
    def _run(self, mode):
        sender = FMV3Sender(udp_port=IOS_PORT, tcp_port=None, fps=30, mode=mode)
        sender.start()
        frames = list(synthetic_frames(fps=30, duration=1.0))
        received = []
        receiver = FMV3Receiver("127.0.0.1", port=IOS_PORT, pc_port=PC_PORT,
                                mode=mode, fps=30)
        thread = threading.Thread(target=receiver.run, args=(received.append,),
                                  kwargs={"duration": 3.0}, daemon=True)
        thread.start()
        sender.run(iter(frames), duration=3.0)
        thread.join(timeout=5)
        sender.stop()
        return frames, received

    def test_fixed52_loopback(self):
        sent, received = self._run(MODE_FIXED52)
        self.assertGreater(len(received), 5)
        first = received[0]
        self.assertTrue(first.tracking)
        self.assertEqual(len(first.blendshapes), 52)
        self.assertAlmostEqual(received[-1].blendshapes["jawOpen"],
                               sent[-1].blendshapes["jawOpen"], places=2)
        self.assertAlmostEqual(received[-1].head[0], sent[-1].head[0], places=3)

    def test_variable_loopback(self):
        sent, received = self._run(MODE_VARIABLE)
        self.assertGreater(len(received), 5)
        self.assertIn("jawOpen", received[-1].blendshapes)
        self.assertAlmostEqual(received[-1].blendshapes["jawOpen"],
                               sent[-1].blendshapes["jawOpen"], places=2)

    def test_tcp_loopback(self):
        sender = FMV3Sender(udp_port=51085, tcp_port=51086, fps=30, mode=MODE_FIXED52)
        sender.start()
        frames = list(synthetic_frames(fps=30, duration=1.0))
        received = []
        receiver = FMV3Receiver("127.0.0.1", port=51086, transport="tcp", mode=MODE_FIXED52)
        thread = threading.Thread(target=receiver.run, args=(received.append,),
                                  kwargs={"duration": 3.0}, daemon=True)
        thread.start()
        sender.run(iter(frames), duration=3.0)
        thread.join(timeout=6)
        sender.stop()
        self.assertGreater(len(received), 5)
        self.assertEqual(len(received[-1].blendshapes), 52)
        self.assertAlmostEqual(received[-1].blendshapes["jawOpen"],
                               frames[-1].blendshapes["jawOpen"], places=2)


if __name__ == "__main__":
    unittest.main()
