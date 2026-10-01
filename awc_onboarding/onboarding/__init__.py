"""AWC Engine Onboarding Toolkit.

A reusable, conversation-driven toolkit for onboarding any third-party,
partner, or open-source engine onto the Cloudera Anywhere Cloud (AWC)
Ecosystem marketplace.

Given a short Q&A session (driven interactively, via an answers file, or
via the bundled MCP server), this package produces a ready-to-apply bundle
of Anywhere Cloud Ecosystem custom resources (Capability, ClusterRequirements,
Engine, Operator, Blueprint, ChartCatalog, ImageCatalog, RBAC) and validates
it against house-keeping standards before anyone runs `kubectl apply`.
"""

from .version import __version__

__all__ = ["__version__"]
