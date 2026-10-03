import io
import os
import tempfile
import unittest

from PIL import Image

from server import config
from server.algorithms import util
from server.image_store import THUMBNAIL_VERSION, ImageStore


def transparent_png(size=(16, 12)):
    buf = io.BytesIO()
    img = Image.new("RGBA", size, (255, 0, 0, 0))
    img.save(buf, "PNG")
    return buf.getvalue()


class TransparencyPolicyTest(unittest.TestCase):
    def test_ensure_rgb_flattens_alpha_to_configured_white(self):
        img = Image.new("RGBA", (2, 1), (255, 0, 0, 0))

        rgb = util.ensure_rgb(img)

        self.assertEqual(rgb.mode, "RGB")
        self.assertEqual(rgb.getpixel((0, 0)), config.TRANSPARENT_BACKGROUND)

    def test_indexed_transparency_is_also_flattened_to_white(self):
        indexed = Image.new("P", (1, 1))
        indexed.putpalette([255, 0, 0, 255, 255, 255])
        indexed.putpixel((0, 0), 0)
        indexed.info["transparency"] = 0

        rgb = util.ensure_rgb(indexed)

        self.assertEqual(rgb.mode, "RGB")
        self.assertEqual(rgb.getpixel((0, 0)), config.TRANSPARENT_BACKGROUND)

    def test_thumbnail_uses_same_white_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_data = config.BASE_DIR, config.DATA_DIR
            config.BASE_DIR = tmp
            config.DATA_DIR = os.path.join(tmp, "data")
            config.IMAGES_DIR = os.path.join(config.DATA_DIR, "images")
            config.THUMBS_DIR = os.path.join(config.DATA_DIR, "thumbnails")
            config.META_DIR = os.path.join(config.DATA_DIR, "metadata")
            config.IMAGES_JSON = os.path.join(config.META_DIR, "images.json")
            try:
                config.ensure_dirs()
                store = ImageStore()
                rec = store.save_upload(transparent_png(), "transparent.png")

                with Image.open(store.thumbnail_path(rec["id"])) as thumb:
                    self.assertEqual(thumb.mode, "RGB")
                    self.assertEqual(thumb.convert("RGB").getpixel((0, 0)),
                                     config.TRANSPARENT_BACKGROUND)
                self.assertEqual(store.get(rec["id"])["thumbnail_version"], THUMBNAIL_VERSION)
            finally:
                config.BASE_DIR, config.DATA_DIR = old_data
                config.IMAGES_DIR = os.path.join(config.DATA_DIR, "images")
                config.THUMBS_DIR = os.path.join(config.DATA_DIR, "thumbnails")
                config.META_DIR = os.path.join(config.DATA_DIR, "metadata")
                config.IMAGES_JSON = os.path.join(config.META_DIR, "images.json")


if __name__ == "__main__":
    unittest.main()
