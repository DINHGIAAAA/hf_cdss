import pytest

from app.modules.profile_avatars import save_avatar_file, validate_avatar_upload


def test_validate_avatar_rejects_empty() -> None:
    with pytest.raises(ValueError, match="Empty"):
        validate_avatar_upload(data=b"", content_type="image/png")


def test_validate_avatar_accepts_png() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    assert validate_avatar_upload(data=png, content_type="image/png") == "image/png"


def test_save_avatar_writes_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.profile_avatars.avatar_upload_dir",
        lambda: tmp_path,
    )
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    key = save_avatar_file(user_id="user_1", data=png, media_type="image/png")
    assert key == "user_1.png"
    assert (tmp_path / key).is_file()
