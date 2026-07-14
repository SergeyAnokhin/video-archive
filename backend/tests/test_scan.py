"""`discover_filesystem()` classification tests (Data Model): video vs.
standalone image vs. a video's own `.jpg` preview collage (never an
independent row), and the interaction between the two (post-V1, user
request -- images are first-class library items too).
"""

from __future__ import annotations

from app.scan import discover_filesystem
from app.sources import SourceAccess
from app.sources.local_backend import LocalBackend


def _discover(root):
    access = SourceAccess(LocalBackend(root), "local")
    return discover_filesystem(access)


def test_standalone_image_is_classified_as_image_not_video(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"fake-jpeg")

    _dirs, files = _discover(tmp_path)

    assert files["photo.jpg"]["is_image_supported"] is True
    assert files["photo.jpg"]["is_video_supported"] is False


def test_image_matching_video_stem_is_absorbed_as_collage_not_a_row(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"fake-video")
    (tmp_path / "clip.jpg").write_bytes(b"fake-collage")

    _dirs, files = _discover(tmp_path)

    assert set(files) == {"clip.mp4"}
    assert files["clip.mp4"]["is_video_supported"] is True
    assert files["clip.mp4"]["has_preview_asset"] is True


def test_various_image_extensions_are_all_recognized(tmp_path):
    for name in ("a.png", "b.gif", "c.webp", "d.bmp", "e.tiff"):
        (tmp_path / name).write_bytes(b"fake-image")

    _dirs, files = _discover(tmp_path)

    for name in ("a.png", "b.gif", "c.webp", "d.bmp", "e.tiff"):
        assert files[name]["is_image_supported"] is True
        assert files[name]["is_video_supported"] is False


def test_unsupported_file_is_neither_video_nor_image(tmp_path):
    (tmp_path / "notes.txt").write_bytes(b"hello")

    _dirs, files = _discover(tmp_path)

    assert files["notes.txt"]["is_video_supported"] is False
    assert files["notes.txt"]["is_image_supported"] is False
