import pytest

from pawabase_iac import P, all_of, any_of, not_


def test_comparisons_build_conditions():
    assert (P.record.owner_id == P.auth.user_id).json() == {"eq": ["$record.owner_id", "$auth.user_id"]}
    assert (P.input.amount >= 10).json() == {"gte": ["$input.amount", 10]}
    assert P.auth.plan.in_(["pro", "team"]).json() == {"in": ["$auth.plan", ["pro", "team"]]}
    assert P.record.title.matches("^draft").json() == {"matches": ["$record.title", "^draft"]}


def test_combinators_flatten_and_nest():
    cond = P.authenticated() & P.role("admin") & (P.input.x > 1)
    assert cond.json() == {"all": [{"authenticated": True}, {"role": "admin"}, {"gt": ["$input.x", 1]}]}
    assert (P.role("a") | P.role("b") | P.role("c")).json() == {"any": [{"role": "a"}, {"role": "b"}, {"role": "c"}]}
    assert (~P.service()).json() == {"not": {"service": True}}
    assert all_of(True, any_of(P.role("a"), False)).json() == {"all": [True, {"any": [{"role": "a"}, False]}]}
    assert not_(P.owner()).json() == {"not": {"owner": "owner_id"}}


def test_a_condition_cannot_be_used_with_python_logic():
    with pytest.raises(TypeError):
        bool(P.role("a"))
    with pytest.raises(TypeError):
        _ = P.role("a") and P.role("b")


def test_literals_that_look_like_paths_are_escaped():
    assert (P.record.note == "$5 off").json() == {"eq": ["$record.note", "$$5 off"]}


def test_flow_paths_work_in_conditions():
    assert (P.steps.load.output.total > 100).json() == {"gt": ["$steps.load.output.total", 100]}
