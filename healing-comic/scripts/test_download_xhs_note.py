"""Offline validation tests; the actual remote download runs only in Actions."""
import io
import json
import unittest

from PIL import Image
import download_xhs_note as d


class DownloaderTests(unittest.TestCase):
    def test_parse_matching_note(self):
        state = {"note": {"noteDetailMap": {"abc": {"note": {
            "title": "和你一起奔夕阳 噜噜噜妹壁纸",
            "imageList": [{"urlDefault": "https://sns-img.xhscdn.com/sample"}],
        }}}}}
        title, images = d.parse_note("<script>window.__INITIAL_STATE__=" + json.dumps(state, ensure_ascii=False) + ";</script>")
        self.assertIn(d.EXPECTED_TITLE, title)
        self.assertEqual(d.image_url(images[0]), "https://sns-img.xhscdn.com/sample")

    def test_reject_unrelated_or_blocked_page(self):
        with self.assertRaises(ValueError):
            d.parse_note("<html>login or verification</html>")
        with self.assertRaises(ValueError):
            d.parse_note('window.__INITIAL_STATE__={"note":{"noteDetailMap":{}}}')
        self.assertFalse(d.allowed_url("https://xhscdn.com.attacker.example/x", d.IMAGE_DOMAINS))
        self.assertFalse(d.allowed_url("https://attacker.example@xhscdn.com/x", d.IMAGE_DOMAINS))
        self.assertFalse(d.allowed_url("http://xhscdn.com/x", d.IMAGE_DOMAINS))

    def test_image_decode_and_corrupt_rejection(self):
        # Use noisy enough image data to exceed the minimum byte requirement.
        image = Image.effect_noise((500, 500), 100).convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        data = buf.getvalue()
        self.assertEqual(d.validate(data), ("png", (500, 500)))
        with self.assertRaises(Exception):
            d.validate(data[:100])
        with self.assertRaises(Exception):
            d.validate(b"<html>not an image</html>" * 1000)


if __name__ == "__main__":
    unittest.main()
