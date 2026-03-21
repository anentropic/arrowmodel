"""Basic tests for arrowdantic."""

import arrowdantic


def test_package_has_all():
    assert hasattr(arrowdantic, "__all__")


def test_core_module_exposed():
    assert hasattr(arrowdantic, "_core")
