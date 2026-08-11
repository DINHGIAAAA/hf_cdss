from app.modules.chat.language import detect_message_language, resolve_chat_language


def test_detect_message_language_vietnamese_diacritics() -> None:
    assert detect_message_language("Nên dùng ARNI không?") == "vi"


def test_detect_message_language_english_question() -> None:
    assert detect_message_language("Should I start ARNI for this patient?") == "en"


def test_detect_message_language_ascii_vietnamese_hint() -> None:
    assert detect_message_language("Co nen them beta blocker khong?") == "vi"


def test_resolve_chat_language_prefers_detected_over_ui_default() -> None:
    assert resolve_chat_language("What about ARNI?", "vi") == "en"
    assert resolve_chat_language("Nên dùng ARNI?", "en") == "vi"
