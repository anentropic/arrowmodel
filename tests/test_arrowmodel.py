"""Basic tests for arrowmodel."""

import arrowmodel


def test_package_has_all():
    assert hasattr(arrowmodel, "__all__")


def test_core_module_exposed():
    assert hasattr(arrowmodel, "_core")
