"""透明背景口径一致性回归测试。

复现并验证：带透明通道的图，列表缩略图与处理结果（锐化/风格/滤镜/批量/对比）
必须使用同一底色（util.FLATTEN_BACKGROUND），不透明图行为不变。

运行：python tests/test_alpha_consistency.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from server import config  # noqa: E402
from server.algorithms import filters, style, util  # noqa: E402
from server.batch import load_working_image  # noqa: E402
from server.image_store import ImageStore  # noqa: E402

BG = util.FLATTEN_BACKGROUND


def _transparent_png_bytes(w=200, h=160):
    """左半不透明红、右半全透明（透明区原始 RGB 为 0,0,0，旧缩略图会变黑）。"""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x in range(w // 2):
        for y in range(h):
            img.putpixel((x, y), (200, 30, 30, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _palette_transparent_bytes(w=120, h=90):
    """P 模式 + transparency 索引的 PNG（GIF 同源情形）。"""
    img = Image.new("P", (w, h), 0)
    img.putpalette([0, 0, 0, 255, 255, 255] + [0, 0, 0] * 254)
    for x in range(w // 2):
        for y in range(h):
            img.putpixel((x, y), 1)
    img.info["transparency"] = 0
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _corner_pixel(path):
    """缩略图右上角像素——测试图右半为透明区，(2,2) 所在左半是不透明红色。"""
    with Image.open(path) as im:
        return im.convert("RGB").getpixel((im.width - 3, 2))


def _close(c1, c2, tol=12):
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def main():
    config.ensure_dirs()
    store = ImageStore()
    failures = []

    def check(name, cond):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    print("== 1. 透明 PNG：缩略图底色 ==")
    rec = store.save_upload(_transparent_png_bytes(), "alpha_test.png")
    thumb_px = _corner_pixel(store.thumbnail_path(rec["id"]))
    check(f"缩略图透明区为统一底色 {BG}（实际 {thumb_px}）", _close(thumb_px, BG))

    print("== 2. 同一张图：处理链路口径 ==")
    _, work, _ = load_working_image(store, rec["id"])
    check("load_working_image 输出为 RGB（无透明通道）", work.mode == "RGB")
    check("工作副本透明区为统一底色", _close(work.convert("RGB").getpixel((work.width - 3, 2)), BG))

    sharp = filters.sharpen(work, {"amount": 50})
    check("锐化结果透明区为统一底色", _close(sharp.convert("RGB").getpixel((sharp.width - 3, 2)), BG))

    styled = style.apply(work, {"style": "oil", "strength": 100})["image"]
    check("风格迁移结果为 RGB（透明已按统一口径合成）", styled.mode == "RGB")

    sat = filters.saturation(work, {"amount": 20})
    check("滤镜（饱和度）结果透明区为统一底色", _close(sat.getpixel((sat.width - 3, 2)), BG))

    print("== 3. 缩略图 vs 处理结果：同底色一致性 ==")
    check("缩略图底色 == 锐化结果底色", _close(thumb_px, sharp.convert("RGB").getpixel((sharp.width - 3, 2))))

    print("== 4. P 模式透明 PNG ==")
    rec_p = store.save_upload(_palette_transparent_bytes(), "alpha_palette.png")
    thumb_p = _corner_pixel(store.thumbnail_path(rec_p["id"]))
    check(f"P 模式缩略图透明区为统一底色（实际 {thumb_p}）", _close(thumb_p, BG))
    rgb_p = util.ensure_rgb(Image.open(store.file_path(rec_p["id"])))
    check("P 模式 ensure_rgb 合成到统一底色", _close(rgb_p.getpixel((rgb_p.width - 3, 2)), BG))

    print("== 5. 不透明图回归 ==")
    opaque = Image.new("RGB", (100, 80), (10, 120, 200))
    buf = io.BytesIO()
    opaque.save(buf, "PNG")
    rec_o = store.save_upload(buf.getvalue(), "opaque.png")
    thumb_o = _corner_pixel(store.thumbnail_path(rec_o["id"]))
    check("不透明图缩略图颜色不变", _close(thumb_o, (10, 120, 200)))
    check("不透明图 ensure_rgb 原样返回", util.ensure_rgb(opaque) is opaque)

    print("== 6. 存量缩略图重建 ==")
    # 模拟旧版黑底缩略图 + 旧版本号
    black = Image.new("RGB", (50, 50), (0, 0, 0))
    black.save(store.thumbnail_path(rec["id"]), "JPEG")
    marker = os.path.join(config.THUMBS_DIR, ".version")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("1")
    n = store.ensure_thumbnails_current()
    rebuilt_px = _corner_pixel(store.thumbnail_path(rec["id"]))
    check(f"版本升级触发重建（{n} 张）", n > 0)
    check(f"重建后透明区为统一底色（实际 {rebuilt_px}）", _close(rebuilt_px, BG))
    check("版本号已推进，二次调用不重建", store.ensure_thumbnails_current() == 0)

    print()
    if failures:
        print(f"共 {len(failures)} 项失败：{failures}")
        sys.exit(1)
    print("透明口径一致性测试全部通过 ✔")


if __name__ == "__main__":
    main()
