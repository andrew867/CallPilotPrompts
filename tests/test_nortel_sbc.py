# SPDX-License-Identifier: MIT
"""Portable codec checks against the pinned NMCODEC build's synthetic vectors."""

from hashlib import sha256
import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nortel_sbc import Codec, parse_blocks, parse_padded_blocks


def vector(name, samples):
    if name == "silence":
        return bytes(2 * samples)
    if name == "impulse":
        return struct.pack(f"<{samples}h", *(32767 if i == 239 else -32768 if i == 240 else 0
                                            for i in range(samples)))
    if name == "alternate":
        return b"\xff\x7f\x00\x80" * (samples // 2)
    seed = 0x31415926
    words = []
    for _ in range(samples):
        seed = (1664525 * seed + 1013904223) & 0xFFFFFFFF
        words.append((seed >> 16) - 32768)
    return struct.pack(f"<{samples}h", *words)


class SbcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library = os.environ.get("CALLPILOT_SBC_LIBRARY")
        if not library:
            raise unittest.SkipTest("set CALLPILOT_SBC_LIBRARY to the compiled codec")
        cls.codec = Codec(library)

    def test_factory_vectors(self):
        fixtures = [
            ("silence", 240, [154],
             "b0bde6aedc2ab572abb5126edf7319f7f6f7073bba2efa5a36d4bfe8ec54ac17",
             "de2b0bcc6577c3778266b6a30cc304b872aa052451943d58a2b80c6a7b5c8325"),
            ("impulse", 257, [226],
             "960000022519e27a6ea1a1b996b5f0dbf3e8e28f3852cf2b525247f5b3504994",
             "c4968a12bc4f188fa7e677ad868d55e94585499601e1112c70e55c9f29fb62df"),
            ("alternate", 512, [226],
             "454ca75655f1f95e2c319d4f19abf2819e3bb82fa32bfe90f676b1408d8624d0",
             "712aeea5be9ac360b2bafc89fb242a01badab8279bc542daa96ec72b92a8bcf9"),
            ("noise", 27648, [8176],
             "84c217cb4a0674216ca8939b63922012385e181baa70f3082ece90e6966644cc",
             "213d6cf7d2d8b399841bf27731e9fedfc03a09293e3d7ed620aca146093c9af3"),
            ("noise", 27649, [8176, 154],
             "8fe6e0f2e2931cd7d0c43a8142d086730f1fe3157ac944e40b8dba70db3278e4",
             "fb4e0a00ecb7f80a0a2e4626f0e06dfb198f1a3e6813b183d88a60cf0c36016a"),
            ("noise", 32768, [8176, 1576],
             "f22539eb6a3073ee8c1a76ef5b59da821ca34fec8150181625785d5898d62ec6",
             "881a9cb34702f159c19364ab7198949a8ce3942c3710e00d68de941d1c9c3239"),
        ]
        for name, length, block_sizes, sbc_hash, pcm_hash in fixtures:
            with self.subTest(name=name, samples=length):
                pcm = vector(name, length)
                encoded = self.codec.encode(pcm)
                self.assertEqual(sha256(encoded).hexdigest(), sbc_hash)
                blocks = list(parse_blocks(encoded))
                self.assertEqual([len(block) for block, _ in blocks], block_sizes)
                decoded = self.codec.decode(encoded)
                self.assertEqual(sha256(decoded).hexdigest(), pcm_hash)
                self.assertEqual(len(decoded) // 2, ((length + 255) // 256) * 256)
                padded = self.codec.encode(pcm, padded=True)
                self.assertEqual(len(padded), 8192 * len(blocks))
                self.assertEqual(list(parse_padded_blocks(padded)), blocks)
                self.assertEqual(self.codec.decode(padded, padded=True), decoded)

    def test_rejects_truncated_and_unsupported_inputs(self):
        with self.assertRaisesRegex(ValueError, "240"):
            self.codec.encode(vector("silence", 239))
        self.assertEqual(self.codec.decode(b""), b"")
        encoded = bytearray(self.codec.encode(vector("silence", 240)))
        with self.assertRaises(ValueError):
            self.codec.decode(bytes(encoded[:-1]))
        encoded[9] = 0
        with self.assertRaisesRegex(ValueError, "invalid SBC block"):
            self.codec.decode(bytes(encoded))
        padded = bytearray(self.codec.encode(vector("silence", 240), padded=True))
        padded[-1] = 1
        with self.assertRaisesRegex(ValueError, "padding"):
            self.codec.decode(bytes(padded), padded=True)


if __name__ == "__main__":
    unittest.main()
