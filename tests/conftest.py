import pytest

from pawabase_iac import collecting


@pytest.fixture()
def project():
    """A fresh registry: definitions made inside a test do not leak into the next one."""
    with collecting() as registry:
        yield registry
