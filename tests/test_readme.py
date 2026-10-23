"""Every Python example in the README runs and builds valid definitions."""

import re
from pathlib import Path

import pytest

from pawabase_iac import collecting

README = Path(__file__).resolve().parent.parent / "README.md"
BLOCKS = re.findall(r"```python\n(.*?)```", README.read_text(), re.S)


def test_the_readme_has_examples():
    assert len(BLOCKS) >= 3


@pytest.mark.parametrize("index", range(len(BLOCKS)))
def test_each_example_runs_and_each_definition_it_makes_is_valid(index):
    with collecting() as registry:
        exec(compile(BLOCKS[index], f"README block {index}", "exec"), {})
    assert registry.items, "the example defines nothing"
    for item in registry.items:
        assert item.problems() == [], (item.label, item.problems())
