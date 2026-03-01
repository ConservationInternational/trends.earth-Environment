# This package is the pluggable "script" module imported by ``gefcore.runner``.
#
# When building the Environment Docker image for a specific analysis, the
# Trends.Earth API replaces ``main.py`` with the concrete script for the
# execution.  The replacement module must expose:
#
#     run(params: dict, logger) -> dict   – execute the analysis
#     REQUIRES_GEE: bool                  – whether GEE init is needed
#
# The default ``main.py`` is a stub that raises ``NotImplementedError``.
