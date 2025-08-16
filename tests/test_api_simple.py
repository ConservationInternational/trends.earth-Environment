"""Tests for the gefcore.api module."""

import pytest

from gefcore import api


class TestAPIModule:
    """Test the API module functionality."""

    def test_module_imports_successfully(self):
        """Test that the API module imports without errors."""
        # This is testing the basic import and initialization
        assert hasattr(api, "login")
        assert hasattr(api, "make_authenticated_request")
        assert hasattr(api, "get_params")
        assert hasattr(api, "patch_execution")
        assert hasattr(api, "save_log")

    def test_require_var_function(self):
        """Test the _require_var helper function."""
        # Test with valid variable
        api._require_var("test_value", "TEST_VAR")  # Should not raise

        # Test with None/empty variable
        with pytest.raises(
            RuntimeError, match="Environment variable 'TEST_VAR' is required"
        ):
            api._require_var(None, "TEST_VAR")

        with pytest.raises(
            RuntimeError, match="Environment variable 'TEST_VAR' is required"
        ):
            api._require_var("", "TEST_VAR")
