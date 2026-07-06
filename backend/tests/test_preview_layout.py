from __future__ import annotations

import unittest

from app.frame_sampling import preview_sample_indices, unique_sample_indices
from app.preview_layout import build_preview_layout, shuffle_indices


class PreviewLayoutTests(unittest.TestCase):
    def test_build_preview_layout_respects_shuffle_order_and_large_tiles(self) -> None:
        layout = build_preview_layout(sample_count=9, large_tile_count=2, timeline_flow="shuffle", aspect_ratio_preset="video")

        self.assertEqual(layout["sample_count"], 9)
        self.assertEqual(layout["large_tile_count"], 2)
        self.assertTrue(layout["tiles"][0]["is_large"])
        self.assertTrue(layout["tiles"][1]["is_large"])
        self.assertEqual([tile["slot_index"] for tile in layout["tiles"]], list(range(9)))

    def test_preview_sampling_keeps_requested_slot_count(self) -> None:
        self.assertEqual(preview_sample_indices(frame_count=1, sample_count=4), [0, 0, 0, 0])
        self.assertEqual(len(preview_sample_indices(frame_count=10, sample_count=6)), 6)

    def test_unique_sampling_deduplicates_for_tagging(self) -> None:
        self.assertEqual(unique_sample_indices(frame_count=0, sample_count=5), [])
        self.assertEqual(unique_sample_indices(frame_count=3, sample_count=8), [1, 2])

    def test_shuffle_indices_alternates_edges(self) -> None:
        self.assertEqual(shuffle_indices(0), [])
        self.assertEqual(shuffle_indices(1), [0])
        self.assertEqual(shuffle_indices(5), [0, 4, 1, 3, 2])


if __name__ == "__main__":
    unittest.main()
