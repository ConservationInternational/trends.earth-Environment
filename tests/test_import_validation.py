"""Test import validation for all Python modules.

Note: Syntax validation (duplicate functions, empty functions, etc.) is already
handled by Ruff linting and doesn't need to be duplicated in tests.
"""

import importlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest


class TestImportValidation:
    """Test import validation of modules."""

    def test_all_modules_importable(self):
        """Test that all main modules can be imported without errors."""
        modules_to_test = [
            "gefcore",
            "gefcore.api",
            "gefcore.loggers",
            "gefcore.runner",
        ]
        import_errors = []

        for module_name in modules_to_test:
            try:
                # Check if module can be found
                spec = importlib.util.find_spec(module_name)
                if spec is None:
                    import_errors.append(f"Module {module_name} not found")
                    continue

                # Try to load the module
                module = importlib.util.module_from_spec(spec)
                if spec.loader:
                    spec.loader.exec_module(module)

            except Exception as e:
                import_errors.append(f"Failed to import {module_name}: {e}")

        if import_errors:
            pytest.fail("Import errors found:\n" + "\n".join(import_errors))

    def test_main_py_importable(self):
        """Test that main.py can be imported without errors."""
        try:
            # Add project root to sys.path temporarily
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            spec = importlib.util.find_spec("main")
            if spec is None:
                pytest.fail("main.py module not found")

            module = importlib.util.module_from_spec(spec)
            if spec.loader:
                spec.loader.exec_module(module)

        except Exception as e:
            pytest.fail(f"Failed to import main.py: {e}")

    def test_gefcore_init_importable(self):
        """Test that gefcore.__init__.py can be imported in test mode."""
        try:
            # Set test environment to prevent actual execution
            os.environ["ENV"] = "test"

            import gefcore

            # Check that the module has expected attributes
            assert hasattr(gefcore, "logger")
            assert hasattr(gefcore, "handle_exception")

        except Exception as e:
            pytest.fail(f"Failed to import gefcore: {e}")
