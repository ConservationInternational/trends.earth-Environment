"""Simple test to debug API test discovery."""


def test_simple():
    """A simple test that should be discovered."""
    assert True


class TestSimple:
    """A simple test class."""

    def test_method(self):
        """A simple test method."""
        assert True
