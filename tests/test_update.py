import unittest
from tuxcontrol.update import latest_viewer_in_feed, _ver


FEED_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>N-able Take Control Status</title>
    <item>
      <title>Release: Take Control Integrated Linux Viewer 7.44.08</title>
      <description>Linux Viewer 7.44.08 is now available.</description>
    </item>
    <item>
      <title>Release: Linux Viewer 7.43.00</title>
      <description>Previous release.</description>
    </item>
  </channel>
</rss>"""

EMPTY_FEED = """<?xml version="1.0"?>
<rss><channel><title>Nothing here</title></channel></rss>"""


class TestLatestViewerInFeed(unittest.TestCase):
    def test_picks_latest(self):
        result = latest_viewer_in_feed(FEED_SAMPLE)
        self.assertEqual(result, "7.44.08")

    def test_empty_feed_returns_none(self):
        self.assertIsNone(latest_viewer_in_feed(EMPTY_FEED))

    def test_none_input(self):
        self.assertIsNone(latest_viewer_in_feed(None))

    def test_empty_string(self):
        self.assertIsNone(latest_viewer_in_feed(""))

    def test_multiple_versions_picks_max(self):
        text = "Linux Viewer 7.40.00\nLinux Viewer 7.44.08\nLinux Viewer 7.41.05\n"
        self.assertEqual(latest_viewer_in_feed(text), "7.44.08")


class TestVer(unittest.TestCase):
    def test_three_parts(self):
        self.assertEqual(_ver("7.44.08"), (7, 44, 8))

    def test_two_parts(self):
        self.assertEqual(_ver("7.44"), (7, 44))

    def test_tag_prefix(self):
        self.assertEqual(_ver("v1.2.3"), (1, 2, 3))

    def test_comparison(self):
        self.assertGreater(_ver("7.44.08"), _ver("7.43.00"))
        self.assertLess(_ver("7.43.00"), _ver("7.44.08"))
        self.assertEqual(_ver("7.44.08"), _ver("7.44.08"))
