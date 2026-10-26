import re

from conductor import ids


def test_new_ids_are_32_lowercase_hex_and_differ() -> None:
    first = ids.new_id()
    second = ids.new_id()
    assert re.fullmatch(r"[0-9a-f]{32}", first)
    assert re.fullmatch(r"[0-9a-f]{32}", second)
    assert first != second
