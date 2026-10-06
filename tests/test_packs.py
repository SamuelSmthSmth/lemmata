"""The pack format (aether.packs): the bundled packs meet it, and it says what is wrong."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from aether import packs
from aether.packs import PackError, load_pack, load_packs, pack_label, validate_pack

COURSES = Path(__file__).resolve().parent.parent / "courses"

MINIMAL = {
    "format": 1,
    "name": "someone/group-basics",
    "version": "0.1.0",
    "title": "Group basics",
    "summary": "A topic pack with no course code.",
    "license": "CC-BY-SA-4.0",
    "chapters": [{"id": "1", "title": "Groups"}],
    "entries": [
        {
            "id": "inverse-of-inverse",
            "chapter": "1",
            "ref": "Lemma 1",
            "title": "Inverse of an inverse",
            "kind": "proof",
            "expected": "VALID",
            "source": "Assume Group(G, op, e, inv)\nLet a : G\nStep: inv(inv(a)) = a\n",
        }
    ],
}


def test_the_bundled_packs_are_valid() -> None:
    names = [p["name"] for p in load_packs(COURSES)]
    assert names == ["core/mth2008", "core/mth2010", "core/notation"]


def test_a_course_code_is_optional() -> None:
    pack, errors = validate_pack(MINIMAL)
    assert errors == [] and pack is not None
    assert pack["courses"] == [] and pack["depends"] == {}
    assert pack_label(pack) == "Group basics"
    assert pack_label({**pack, "courses": ["MTH2010"]}) == "MTH2010"


@pytest.mark.parametrize(
    ("change", "complaint"),
    [
        (lambda p: p.pop("name"), "name: missing"),
        (lambda p: p.update(name="Core/MTH2008"), "name: must be scope/slug"),
        (lambda p: p.update(version="1.0"), "version: must be semver"),
        (lambda p: p.update(format=2), "format: expected 1"),
        (lambda p: p.update(colour="red"), "colour: not a pack field"),
        (lambda p: p["entries"][0].update(kind="lemma"), "entries[0].kind"),
        (lambda p: p["entries"][0].update(chapter="9"), "entries[0].chapter"),
        (lambda p: p["entries"][0].update(kind="trap", expected="INVALID"), "entries[0].explanation"),
        (lambda p: p["entries"].append(dict(p["entries"][0])), "entries[1].id"),
    ],
)
def test_problems_are_named_by_where_they_are(change, complaint) -> None:
    data = copy.deepcopy(MINIMAL)
    change(data)
    pack, errors = validate_pack(data)
    assert pack is None and any(complaint in e for e in errors), errors


def test_every_problem_is_reported_not_just_the_first() -> None:
    data = copy.deepcopy(MINIMAL)
    data.pop("title")
    data["version"] = "x"
    assert len(validate_pack(data)[1]) == 2


def test_load_pack_raises_with_every_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": 1}), encoding="utf-8")
    with pytest.raises(PackError) as caught:
        load_pack(bad)
    assert len(caught.value.errors) >= 5


def test_the_json_schema_agrees_on_the_fields() -> None:
    schema = json.loads((COURSES / "pack.schema.json").read_text(encoding="utf-8"))
    assert schema["required"] == list(packs.REQUIRED)
    assert set(schema["properties"]) == set(packs.REQUIRED) | set(packs.OPTIONAL)
    entry = schema["properties"]["entries"]["items"]
    assert entry["required"] == list(packs.ENTRY_REQUIRED)
    assert set(entry["properties"]) == set(packs.ENTRY_REQUIRED) | set(packs.ENTRY_OPTIONAL)
    assert entry["properties"]["kind"]["enum"] == list(packs.KINDS)
    assert entry["properties"]["expected"]["enum"] == list(packs.VERDICTS)
    assert entry["properties"]["level"]["enum"] == list(packs.LEVELS)
    assert schema["properties"]["level"]["enum"] == list(packs.LEVELS)


class TestLevels:
    """An entry's expected verdict is at its level: its own, else the pack's, else off."""

    def test_a_pack_without_levels_is_checked_off(self) -> None:
        pack, errors = validate_pack(copy.deepcopy(MINIMAL))
        assert not errors
        assert packs.entry_level(pack, pack["entries"][0]) == "off"
        assert packs.kernel_for("off") is None

    def test_the_pack_level_and_an_entry_override(self) -> None:
        data = copy.deepcopy(MINIMAL)
        data["level"] = "course"
        data["entries"].append({**data["entries"][0], "id": "at-exam", "level": "exam"})
        pack, errors = validate_pack(data)
        assert not errors
        assert [packs.entry_level(pack, e) for e in pack["entries"]] == ["course", "exam"]
        assert packs.kernel_for("exam") == "exam"

    @pytest.mark.parametrize("where", ["pack", "entry"])
    def test_an_unknown_level_is_refused(self, where: str) -> None:
        data = copy.deepcopy(MINIMAL)
        (data if where == "pack" else data["entries"][0])["level"] = "strict"
        pack, errors = validate_pack(data)
        assert pack is None
        assert any("level: must be one of off, exam, course, scratch" in e for e in errors)

    def test_the_core_packs_are_recorded_at_course(self) -> None:
        for pack in load_packs(COURSES):
            assert pack["level"] == "course", pack["name"]
