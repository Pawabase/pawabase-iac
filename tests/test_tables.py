from pawabase_iac import (
    P, Policy, Allow, Array, BelongsTo, Boolean, Desc, Index, Integer, Where, Number, Object, Ref, Schema, String, Table, Transformer, crud, read_only,
)
from pawabase_iac.validate import check


def test_fields_hold_only_what_was_set():
    assert String("name", required=True, max_length=10) == {"name": "name", "type": "string", "required": True, "max_length": 10}
    assert Boolean("done", default=False) == {"name": "done", "type": "boolean", "default": False}
    assert Array("tags", of=String("tag"))["items"] == {"type": "string"}
    assert Object("a", fields=[Integer("n", minimum=0)])["fields"][0]["minimum"] == 0


def test_crud_and_overrides():
    ops = crud("authenticated", delete=Allow(P.role("admin")))
    assert ops["list"] == {"enabled": True, "policy": "authenticated"}
    assert ops["delete"]["policy"].json() == {"role": "admin"}
    assert set(read_only("public")) == {"list", "get"}


def test_a_valid_table(project):
    t = Table("orders", fields=[Number("total", required=True), String("customer_id")], operations=crud("authenticated"),
              relations=[BelongsTo("customer", "customers", "customer_id")], indexes=[Index("customer_id")])
    Table("customers", fields=[String("name")])
    assert t.problems() == []
    assert check(project.items) == []


def test_table_problems(project):
    bad = Table("Orders", fields=[String("a"), String("a"), {"name": "x", "type": "nope"}], id_type="int",  # type: ignore[arg-type]
                operations={"explode": Allow()}, indexes=[Index("ghost")], cache_ttl=999999)
    messages = " | ".join(bad.problems())
    for expected in ("not a valid name", "duplicate field", "unknown type", "id_type", "explode", "'ghost' is not a column of this table", "cache_ttl"):
        assert expected in messages


def test_references_are_checked_across_definitions(project):
    Table("orders", fields=[String("customer_id")], operations={"list": Allow("ghost_policy")},
          relations=[BelongsTo("customer", "customers", "customer_id")], transformer="ghost_t")
    Table("docs", fields=[Ref("body", schema="GhostSchema")])
    text = "\n".join(map(str, check(project.items)))
    assert "'ghost_policy' is not defined" in text
    assert "'customers' is not defined" in text
    assert "'ghost_t' is not defined" in text
    assert "'GhostSchema' is not defined" in text


def test_objects_work_as_references(project):
    mine = Policy("mine", P.owner())
    Schema("Address", fields=[String("city")])
    shape = Transformer("public", omit=["secret"], case="camel")
    Table("a", fields=[String("owner_id")], operations=crud(mine), transformer=shape)
    assert check(project.items) == []
    assert project.items[-1].body()["transformer"] == "public"
    assert project.items[-1].body()["operations"]["list"]["policy"] == "mine"


def test_transformer_steps(project):
    t = Transformer("t", omit=["a"], set={"b": "{{ record.a }}"}, rename={"c": "d"}, case="snake")
    assert t.body()["definition"] == {"omit": ["a"], "set": {"b": "{{ record.a }}"}, "rename": {"c": "d"}, "case": "snake"}
    assert Transformer("empty").problems()


def test_index_builders_and_checks(project):
    assert Index("a", Desc("b"), where=[Where("c", "is_null")], unique=True) == {
        "name": "idx_a_b", "columns": [{"name": "a"}, {"name": "b", "desc": True}], "unique": True, "where": [{"column": "c", "op": "is_null"}],
    }
    assert Index("a", method="hash")["method"] == "hash"
    t = Table("t", fields=[String("a"), String("b")], indexes=[Index("a", "b", method="hash"), Index("a", method="brin", unique=True),
                                                         Index("a", where=[Where("zzz", "=", 1)]), Index("a", name="Bad-Name")])
    text = " | ".join(t.problems())
    for expected in ("hash index covers one column", "only a btree index can be unique", "unknown column 'zzz'", "lowercase letters"):
        assert expected in text


def test_policies_can_only_use_roles_and_permissions_that_exist(project):
    from pawabase_iac import Role

    Role("teacher", permissions=["grades.write"])
    Policy("p1", P.role("teacher") | P.role("ghost"))
    Policy("p2", P.permission("grades.write") & P.permission("nope"))
    Table("t", fields=[String("x")], operations={"list": Allow("role:other")})
    text = "\n".join(map(str, check(project.items)))
    assert "role 'ghost' is not defined" in text and "role 'other' is not defined" in text
    assert "permission 'nope' is not granted by any role" in text
    assert "'teacher'" not in text.replace("(roles: teacher)", "")


def test_without_any_roles_nothing_is_said_about_them(project):
    Policy("p", P.role("whoever"))
    assert check(project.items) == []
