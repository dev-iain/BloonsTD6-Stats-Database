from __future__ import annotations

from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.formatting import EMPTY_RESULTS_MESSAGE
from btd6.query import QueryError, UpgradeFilters
from btd6.ui.presenters import (
    DEBOUNCE_MS,
    SORTABLE_KEYS,
    DatabaseMissingError,
    FilterInputs,
    InputError,
    PopChoice,
    SearchPresenter,
    choice_to_flag,
    count_message,
    next_sort,
    parse_filters,
    parse_threshold,
)
from tests.ui.fakes import DeferredThreads, FakeScheduler, FakeView, make_runner


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", None), ("  ", None), ("0", 0.0), ("2.5", 2.5), (".5", 0.5), (" 7 ", 7.0)],
)
def test_parse_threshold_accepts(text: str, expected: object) -> None:
    assert parse_threshold("Pierce", text) == expected


@pytest.mark.parametrize("text", ["-1", "abc", "nan", "inf", "1e999", "1,5", "--2"])
def test_parse_threshold_rejects(text: str) -> None:
    with pytest.raises(InputError):
        parse_threshold("Pierce", text)


@given(st.floats(min_value=0, max_value=1e9, allow_nan=False))
def test_parse_threshold_round_trips_nonnegative_numbers(number: float) -> None:
    assert parse_threshold("Damage", repr(number)) == number


def test_default_inputs_give_empty_filters() -> None:
    filters, errors = parse_filters(FilterInputs())
    assert errors == {}
    assert filters is not None
    assert all(value is None for value in vars(filters).values())


def test_pop_choices_map_to_flags() -> None:
    inputs = FilterInputs(
        pops={**FilterInputs().pops, "lead": PopChoice.CAN, "glass": PopChoice.CANNOT},
        camo=PopChoice.CAN,
    )
    filters, _ = parse_filters(inputs)
    assert filters.can_pop_lead is True
    assert filters.can_pop_glass is False
    assert filters.can_pop_black is None
    assert filters.can_hit_camo is True


def test_invalid_threshold_returns_no_filters_and_field_error() -> None:
    filters, errors = parse_filters(FilterInputs(min_pierce="x", min_range="-3"))
    assert filters is None
    assert set(errors) == {"min_pierce", "min_range"}


def test_name_text_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    filters, _ = parse_filters(FilterInputs(name_text="  dart "))
    assert filters.tower_name_contains == "dart"


@pytest.mark.parametrize(
    ("choice", "flag"),
    [(PopChoice.ANY, None), (PopChoice.CAN, True), (PopChoice.CANNOT, False)],
)
def test_choice_to_flag(choice: PopChoice, flag: bool | None) -> None:
    assert choice_to_flag(choice) is flag


def test_sortable_keys_exclude_identifier_and_pops() -> None:
    assert "tower_name" not in SORTABLE_KEYS
    assert "pops" not in SORTABLE_KEYS
    assert "path" in SORTABLE_KEYS


def test_first_click_ascending_second_descending_third_ascending() -> None:
    state = next_sort(None, False, "projectile_damage")
    assert state == ("projectile_damage", False)
    state = next_sort(*state, "projectile_damage")
    assert state == ("projectile_damage", True)
    assert next_sort(*state, "projectile_damage") == ("projectile_damage", False)


def test_switching_column_resets_to_ascending() -> None:
    assert next_sort("path", True, "attack_rate") == ("attack_rate", False)


@given(
    st.sampled_from(sorted(SORTABLE_KEYS)), st.booleans(), st.sampled_from(sorted(SORTABLE_KEYS))
)
def test_next_sort_always_lands_on_clicked_column(
    current: str, descending: bool, clicked: str
) -> None:
    assert next_sort(current, descending, clicked)[0] == clicked


def test_next_sort_ignores_unsortable_column() -> None:
    assert next_sort("path", True, "pops") == ("path", True)


@pytest.mark.parametrize(
    ("count", "text"), [(0, "0 upgrades"), (1, "1 upgrade"), (2, "2 upgrades")]
)
def test_count_message(count: int, text: str) -> None:
    assert count_message(count) == text


class Harness:
    def __init__(self) -> None:
        self.view = FakeView()
        self.scheduler = FakeScheduler()
        self.threads = DeferredThreads()
        self.queries: list[tuple] = []
        self.result: list[tuple[str, ...]] | Exception = [("a",)]
        self.presenter = SearchPresenter(
            self.view,
            make_runner(self.scheduler, self.threads),
            self.scheduler,
            run_query=self.run_query,
            run_load=lambda report: "Loaded 3 upgrades",
        )

    def run_query(
        self, filters: UpgradeFilters, sort_by: str | None, descending: bool
    ) -> list[tuple[str, ...]]:
        self.queries.append((filters, sort_by, descending))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def settle(self) -> None:
        self.threads.run_all()
        self.scheduler.fire_all()
        self.threads.run_all()


@pytest.fixture
def harness() -> Harness:
    return Harness()


def test_search_shows_rows_and_count(harness: Harness) -> None:
    harness.result = [("a",), ("b",)]
    harness.presenter.start()
    assert harness.view.busy_states == [True]
    harness.settle()
    assert harness.view.rows == [("a",), ("b",)]
    assert harness.view.last_status == ("2 upgrades", False)
    assert harness.view.busy_states[-1] is False


def test_empty_result_shows_empty_state(harness: Harness) -> None:
    harness.result = []
    harness.presenter.start()
    harness.settle()
    assert harness.view.placeholder == (EMPTY_RESULTS_MESSAGE, False)


def test_filter_changes_are_debounced(harness: Harness) -> None:
    for text in ("d", "da", "dar"):
        harness.presenter.on_filters_changed(FilterInputs(name_text=text))
    assert harness.queries == []
    assert len(harness.scheduler.pending) == 1
    assert next(iter(harness.scheduler.pending.values()))[0] == DEBOUNCE_MS
    assert len(harness.scheduler.cancelled) == 2
    harness.settle()
    assert len(harness.queries) == 1


def test_submit_searches_immediately_and_cancels_debounce(harness: Harness) -> None:
    harness.presenter.on_filters_changed(FilterInputs(min_pierce="3"))
    harness.presenter.on_submit(FilterInputs(min_pierce="3"))
    assert harness.scheduler.cancelled
    harness.settle()
    assert len(harness.queries) == 1
    assert harness.queries[0][0].min_pierce == 3.0


def test_invalid_input_never_reaches_query(harness: Harness) -> None:
    harness.presenter.on_submit(FilterInputs(min_damage="oops"))
    harness.settle()
    assert harness.queries == []
    assert "min_damage" in harness.view.errors
    assert harness.view.last_status[1] is True


def test_errors_clear_once_input_is_fixed(harness: Harness) -> None:
    harness.presenter.on_submit(FilterInputs(min_damage="oops"))
    harness.presenter.on_submit(FilterInputs(min_damage="2"))
    assert harness.view.errors == {}


def test_stale_results_are_dropped(harness: Harness) -> None:
    harness.presenter.on_submit(FilterInputs(min_damage="1"))
    harness.presenter.on_submit(FilterInputs(min_damage="2"))
    first, second = harness.threads.targets
    harness.result = [("new",)]
    second()
    harness.scheduler.fire_all()
    assert harness.view.rows == [("new",)]
    harness.result = [("old",)]
    first()
    harness.scheduler.fire_all()
    assert harness.view.rows == [("new",)]


def test_sort_click_requeries_with_direction(harness: Harness) -> None:
    harness.presenter.on_sort("projectile_damage")
    harness.presenter.on_sort("projectile_damage")
    harness.settle()
    assert [(sort, desc) for _, sort, desc in harness.queries] == [
        ("projectile_damage", False),
        ("projectile_damage", True),
    ]
    assert harness.view.sort == ("projectile_damage", True)


def test_sort_on_unsortable_column_does_nothing(harness: Harness) -> None:
    harness.presenter.on_sort("pops")
    assert harness.queries == []
    assert harness.view.sort is None


def test_reset_restores_defaults_and_searches(harness: Harness) -> None:
    harness.presenter.on_submit(FilterInputs(min_range="9"))
    harness.presenter.reset()
    harness.settle()
    assert harness.view.filters_shown == FilterInputs()
    assert harness.queries[-1][0].min_range is None


def test_missing_database_offers_load(harness: Harness) -> None:
    harness.result = DatabaseMissingError("x")
    harness.presenter.start()
    harness.settle()
    assert harness.view.placeholder[1] is True
    assert harness.view.last_status[1] is False


def test_query_error_is_human_readable(harness: Harness) -> None:
    harness.result = QueryError('Cannot sort by "path"')
    harness.presenter.start()
    harness.settle()
    assert harness.view.last_status == ('Search failed: Cannot sort by "path"', True)


def test_unexpected_error_hides_details(harness: Harness) -> None:
    harness.result = RuntimeError("secret internals")
    harness.presenter.start()
    harness.settle()
    message, is_error = harness.view.last_status
    assert is_error
    assert "secret internals" not in message


def test_load_reports_progress_then_refreshes_table() -> None:
    view, scheduler, threads = FakeView(), FakeScheduler(), DeferredThreads()
    rows = [("a",)]

    def load(report: Callable[[str], None]) -> str:
        report("Loading Wizard Monkey (1 of 4)...")
        return "Loaded 3 upgrades"

    presenter = SearchPresenter(
        view, make_runner(scheduler, threads), scheduler, lambda *args: rows, load
    )
    presenter.load_database()
    threads.run_all()
    scheduler.fire_all()
    assert ("Loading Wizard Monkey (1 of 4)...", False) in view.statuses
    assert ("Loaded 3 upgrades", False) in view.statuses
    threads.run_all()
    scheduler.fire_all()
    assert view.rows == rows


def test_load_failure_shows_error_and_allows_retry() -> None:
    view, scheduler, threads = FakeView(), FakeScheduler(), DeferredThreads()

    def load(report: Callable[[str], None]) -> str:
        raise RuntimeError("could not reach the wiki")

    presenter = SearchPresenter(
        view, make_runner(scheduler, threads), scheduler, lambda *args: [], load
    )
    presenter.load_database()
    presenter.load_database()
    assert len(threads.targets) == 1
    threads.run_all()
    scheduler.fire_all()
    assert view.last_status == ("Load failed: could not reach the wiki", True)
    assert view.busy_states[-1] is False
    presenter.load_database()
    assert len(threads.targets) == 1


def test_close_drops_in_flight_results(harness: Harness) -> None:
    harness.presenter.start()
    harness.presenter.close()
    harness.settle()
    assert harness.view.rows is None
