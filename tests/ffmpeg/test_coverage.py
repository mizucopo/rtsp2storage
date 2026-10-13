"""Coverage and packet continuity contracts for the controlled RTSP fixtures."""

import math
import unittest

import compare


def segment(video_seconds, audio_seconds=None, video_gap=0.04, audio_gap=1024 / 48000):
    if audio_seconds is None:
        audio_seconds = video_seconds
    return {"valid": True, "streams": [
        {"type": "video", "packets": round(video_seconds * 25), "max_dts_gap": video_gap},
        {"type": "audio", "packets": math.ceil(audio_seconds * 48000 / 1024),
         "max_dts_gap": audio_gap},
    ]}


class CoverageTest(unittest.TestCase):
    def coverage(self, files, seconds=13):
        return compare.recording_coverage(files, seconds)

    def test_three_short_decodable_segments_do_not_cover_observation(self):
        result = self.coverage([segment(0.4)] * 3)
        self.assertFalse(result["valid"])
        self.assertLess(result["streams"]["video"]["packet_seconds"], 2)

    def test_missing_interior_segment_with_three_valid_files_fails(self):
        self.assertTrue(self.coverage([segment(4)] * 3 + [segment(1.5)])["valid"])
        self.assertFalse(self.coverage([segment(4)] * 2 + [segment(1.5)])["valid"])

    def test_keyframe_wait_and_short_final_segment_are_allowed(self):
        files = [segment(4, 5.8), segment(4), segment(2), segment(0.1, 0.2)]
        self.assertTrue(self.coverage(files)["valid"])

    def test_video_or_audio_loss_fails_independently(self):
        for video, audio in ((8, 13), (13, 8)):
            with self.subTest(video=video, audio=audio):
                self.assertFalse(self.coverage([segment(video, audio)])["valid"])

    def test_large_timestamp_gap_fails_even_with_enough_packets(self):
        for video_gap, audio_gap in ((0.5, 0.022), (0.04, 0.5)):
            with self.subTest(video_gap=video_gap, audio_gap=audio_gap):
                self.assertFalse(self.coverage([
                    segment(14, video_gap=video_gap, audio_gap=audio_gap)
                ])["valid"])

    def test_volume_tolerance_boundary_and_measured_window(self):
        self.assertTrue(self.coverage([segment(10, 12)])["valid"])
        self.assertFalse(self.coverage([segment(9.96, 12)])["valid"])
        self.assertFalse(self.coverage([segment(10, 11.95)])["valid"])
        self.assertFalse(self.coverage([segment(13)], seconds=20)["valid"])

    def test_gap_threshold_and_fixture_loop_jitter(self):
        self.assertTrue(self.coverage([segment(13, video_gap=0.061322)])["valid"])
        self.assertTrue(self.coverage([segment(13, video_gap=0.08, audio_gap=0.05)])["valid"])
        self.assertFalse(self.coverage([segment(13, video_gap=0.080001)])["valid"])
        self.assertFalse(self.coverage([segment(13, audio_gap=0.050001)])["valid"])

    def test_missing_or_nonfinite_evidence_cannot_pass(self):
        for seconds in (float("nan"), float("inf"), -1, 0):
            with self.subTest(seconds=seconds):
                with self.assertRaises(ValueError):
                    self.coverage([segment(13)], seconds)
        files = [segment(13)]
        files[0]["streams"][0]["max_dts_gap"] = float("nan")
        self.assertFalse(self.coverage(files)["valid"])
        self.assertFalse(self.coverage([])["valid"])


class BaselineComparisonTest(unittest.TestCase):
    def case(self, baseline, alpine, skew=0):
        case = {"variants": {"baseline": {"valid": True, "files": baseline},
                             "alpine": {"valid": True, "files": alpine}}}
        compare.validate_case_coverage(case, 13, skew)
        return case

    def test_large_disparity_fails_despite_both_absolute_floors_passing(self):
        case = self.case([segment(14)], [segment(10.5, 12.5)])
        self.assertFalse(case["coverage_comparison"]["valid"])
        self.assertTrue(all(not v["valid"] for v in case["variants"].values()))

    def test_segmentation_and_launch_skew_are_allowed(self):
        case = self.case([segment(6), segment(4), segment(3.5)],
                         [segment(4), segment(4), segment(4), segment(0.7)])
        self.assertTrue(all(v["valid"] for v in case["variants"].values()))
        self.assertTrue(self.case([segment(15)], [segment(13)], skew=1.1)
                        ["coverage_comparison"]["valid"])

    def test_existing_failure_remains_invalid(self):
        case = {"variants": {"baseline": {"valid": False, "files": [segment(13)]},
                             "alpine": {"valid": True, "files": [segment(13)]}}}
        compare.validate_case_coverage(case, 13, 0)
        self.assertFalse(case["variants"]["baseline"]["valid"])


if __name__ == "__main__":
    unittest.main()
