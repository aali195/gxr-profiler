import pytest

from gxr_core.server import is_local_origin


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("http://127.0.0.1:8766", True),
        ("http://localhost:8766", True),
        ("http://LOCALHOST:8766", True),
        ("http://127.0.0.1.evil.com:8766", False),
        ("http://localhost.evil.com", False),
        ("https://127.0.0.1:8766", False),
        ("http://user@127.0.0.1:8766", False),
        ("null", False),
        ("", False),
        ("not a url", False),
    ],
)
def test_local_origin_accepts_only_exact_loopback_hosts(origin, expected):
    assert is_local_origin(origin) is expected
