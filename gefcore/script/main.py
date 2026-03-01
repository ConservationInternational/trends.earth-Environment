"""Default script entry point for the trends.earth Environment.

``gefcore.runner`` imports this module as::

    from gefcore.script import main
    result = main.run(params, logger)

The ``run`` function must accept ``(params: dict, logger)`` and return a
results dict suitable for ``Execution.results``.

This is a **stub** – it raises ``NotImplementedError``.  The Trends.Earth
API replaces this file with the concrete script for each execution when
building the Environment Docker image.
"""

# Default: GEE is required unless the concrete runner says otherwise.
REQUIRES_GEE = True


def run(params, logger):
    """Placeholder – must be replaced by the concrete script for this execution."""
    raise NotImplementedError(
        "gefcore.script.main.run() is a stub. "
        "The Trends.Earth API must replace gefcore/script/main.py with the "
        "concrete script for this execution when building the Docker image."
    )


__all__ = ["run", "REQUIRES_GEE"]
