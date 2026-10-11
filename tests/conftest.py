"""Bendri fixture'ai HA testams."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """`custom_components/` įkeliamas tik su šiuo fixture'u."""
    yield
