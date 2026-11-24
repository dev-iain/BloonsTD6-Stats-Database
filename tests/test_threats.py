from __future__ import annotations

import sqlite3

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.db import apply_migrations, connect
from btd6.db.connection import DEFAULT_DATABASE_PATH
from btd6.rounds import NoRoundDataError, get_round
from btd6.threats import PROPERTY_NAMES, RoundThreats, round_threats
from tests.rounds_fixture import LAYERS, LEAD_RBE_FORT, build_rounds_db

MIXED_ROUND = {3: [("Red", 5, False), ("Blue", 3, False), ("Lead", 2, False)]}


def threats_for(
    extra_rounds: dict[int, list[tuple[str, int, bool]]],
    round_number: int,
    *updates: str,
) -> RoundThreats:
    connection = build_rounds_db(extra_rounds)
    for statement in updates:
        connection.execute(statement)
    return round_threats(connection, round_number)


def test_round_threats_mixed_round() -> None:
    result = threats_for(MIXED_ROUND, 3)
    assert result.round == 3
    assert result.total_rbe == 57
    assert result.unknown_groups == 0
    assert result.property_share["lead"] == pytest.approx(46 / 57)
    assert [result.property_share[name] for name in PROPERTY_NAMES if name != "lead"] == [0.0] * 5
    assert result.camo_share == 0.0
    assert result.regrow_share == 0.0
    assert result.moab_share == 0.0
    expected_layers = (5 * LAYERS["Red"] + 6 * LAYERS["Blue"] + 46 * LAYERS["Lead"]) / 57
    assert result.mean_layers == pytest.approx(expected_layers)


def test_round_threats_property_names() -> None:
    assert PROPERTY_NAMES == ("lead", "black", "white", "purple", "glass", "frozen")
    assert set(threats_for(MIXED_ROUND, 3).property_share) == set(PROPERTY_NAMES)


def test_round_threats_empty_round() -> None:
    connection = build_rounds_db()
    connection.execute("DELETE FROM round_groups WHERE round = 5")
    result = round_threats(connection, 5)
    assert result.total_rbe == 0
    assert result.unknown_groups == 0
    assert result.mean_layers == 0.0
    assert result.moab_share == 0.0
    assert set(result.property_share.values()) == {0.0}


def test_round_threats_only_camo() -> None:
    result = threats_for({}, 24)
    assert result.camo_share == 1.0
    assert result.property_share["lead"] == 0.0


def test_round_threats_only_lead() -> None:
    result = threats_for({}, 27)
    assert result.property_share["lead"] == 1.0
    assert result.camo_share == 0.0


def test_round_threats_moab_only() -> None:
    result = threats_for({40: [("Moab", 1, False)]}, 40)
    assert result.moab_share == 1.0
    assert result.total_rbe == 616


def test_round_threats_mixed_moab_share() -> None:
    result = threats_for({}, 40)
    assert result.moab_share == pytest.approx(616 / (20 * 5 + 616))


def test_round_threats_fortified_uses_rbe_fort() -> None:
    result = threats_for({}, 27, "UPDATE round_groups SET is_fortified = 1 WHERE round = 27")
    assert result.total_rbe == 6 * LEAD_RBE_FORT


def test_round_threats_fortified_null_rbe_fort() -> None:
    result = threats_for(
        {},
        27,
        "UPDATE round_groups SET is_fortified = 1 WHERE round = 27",
        "UPDATE bloons SET rbe_fort = NULL",
    )
    assert result.total_rbe == 6 * 23


def test_round_threats_regrow_share() -> None:
    result = threats_for(
        MIXED_ROUND, 3, "UPDATE round_groups SET is_regrow = 1 WHERE round = 3 AND bloon_id = 2"
    )
    assert result.regrow_share == pytest.approx(6 / 57)


def test_round_threats_null_rbe_group() -> None:
    result = threats_for(MIXED_ROUND, 3, "UPDATE bloons SET rbe = NULL WHERE name = 'Blue'")
    assert result.unknown_groups == 1
    assert result.total_rbe == 5 + 46
    assert result.property_share["lead"] == pytest.approx(46 / 51)


def test_round_threats_only_unknown_group() -> None:
    result = threats_for({}, 27, "UPDATE bloons SET rbe = NULL")
    assert result.total_rbe == 0
    assert result.unknown_groups == 1
    assert result.property_share["lead"] == 0.0


def test_round_threats_group_counts_toward_every_property() -> None:
    result = threats_for(
        {}, 27, "UPDATE bloons SET has_black = 1, has_glass = 1 WHERE name = 'Lead'"
    )
    shares = result.property_share
    assert (shares["lead"], shares["black"], shares["glass"]) == (1.0, 1.0, 1.0)


@pytest.mark.parametrize("round_number", [0, -1, 41])
def test_round_threats_round_out_of_range(round_number: int) -> None:
    with pytest.raises(ValueError, match="not loaded"):
        round_threats(build_rounds_db(), round_number)


def test_round_threats_no_round_data() -> None:
    connection = connect(":memory:")
    apply_migrations(connection)
    with pytest.raises(NoRoundDataError):
        round_threats(connection, 1)
    connection.close()


@pytest.mark.parametrize("round_number", ["3", True, 3.0])
def test_round_threats_wrong_type(round_number: object) -> None:
    with pytest.raises(TypeError):
        round_threats(build_rounds_db(), round_number)


GROUP = st.tuples(
    st.sampled_from(["Red", "Blue", "Pink", "Lead", "Ceramic", "Moab"]),
    st.integers(min_value=1, max_value=50),
    st.booleans(),
)


@given(groups=st.lists(GROUP, min_size=1, max_size=6))
def test_round_threats_shares_within_unit_interval(groups: list[tuple[str, int, bool]]) -> None:
    connection = build_rounds_db({10: groups})
    result = round_threats(connection, 10)
    shares = [*result.property_share.values(), result.camo_share, result.regrow_share]
    assert all(0.0 <= share <= 1.0 for share in shares + [result.moab_share])
    moab_rbe = sum(
        group.count * (group.rbe or 0) for group in get_round(connection, 10) if group.is_moab
    )
    assert result.moab_share + (result.total_rbe - moab_rbe) / result.total_rbe == pytest.approx(
        1.0
    )


def test_round_threats_is_frozen_dataclass() -> None:
    result = threats_for({}, 1)
    with pytest.raises(AttributeError):
        result.total_rbe = 0  # type: ignore[misc]


def test_round_threats_db_is_untouched() -> None:
    connection = build_rounds_db()
    before = connection.total_changes
    round_threats(connection, 3)
    assert connection.total_changes == before
    assert isinstance(connection, sqlite3.Connection)


@pytest.fixture
def real_database() -> sqlite3.Connection:
    if not DEFAULT_DATABASE_PATH.exists():
        pytest.skip("btd6.db is not loaded")
    connection = connect(DEFAULT_DATABASE_PATH)
    loaded = connection.execute("SELECT COUNT(*) FROM round_groups").fetchone()[0]
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(bloons)")]
    if loaded == 0 or "has_lead" not in columns:
        pytest.skip("btd6.db has no rounds or bloon properties")
    return connection


def test_round_threats_round_40_has_moab(real_database) -> None:
    assert round_threats(real_database, 40).moab_share > 0


def test_round_threats_round_63_lead_is_largest_property(real_database) -> None:
    shares = round_threats(real_database, 63).property_share
    assert shares["lead"] > 0
    assert shares["lead"] == max(shares.values())


def test_round_threats_null_layers_count_as_zero() -> None:
    result = threats_for({}, 27, "UPDATE bloons SET layers = NULL")
    assert result.total_rbe == 138
    assert result.mean_layers == 0.0
