from __future__ import annotations

from collections.abc import Callable

from tests.ui.fakes import DeferredThreads, FakeScheduler, make_runner


def build() -> tuple[FakeScheduler, DeferredThreads, list]:
    scheduler, threads = FakeScheduler(), DeferredThreads()
    return scheduler, threads, []


def test_success_callback_runs_only_when_polled() -> None:
    scheduler, threads, events = build()
    runner = make_runner(scheduler, threads)
    runner.submit(lambda report: 42, events.append, events.append)
    threads.run_all()
    assert events == []
    scheduler.fire_all()
    assert events == [42]


def test_error_callback_receives_exception() -> None:
    scheduler, threads, events = build()
    runner = make_runner(scheduler, threads)

    def failing(report: Callable[[str], None]) -> None:
        raise ValueError("boom")

    runner.submit(failing, events.append, events.append)
    threads.run_all()
    scheduler.fire_all()
    assert isinstance(events[0], ValueError)


def test_progress_messages_reach_callback_before_result() -> None:
    scheduler, threads, events = build()
    runner = make_runner(scheduler, threads)

    def work(report: Callable[[str], None]) -> str:
        report("step 1")
        return "done"

    runner.submit(work, events.append, events.append, on_progress=events.append)
    threads.run_all()
    scheduler.fire_all()
    assert events == ["step 1", "done"]


def test_polling_stops_when_no_jobs_remain() -> None:
    scheduler, threads, events = build()
    runner = make_runner(scheduler, threads)
    runner.submit(lambda report: 1, events.append, events.append)
    threads.run_all()
    scheduler.fire_all()
    assert scheduler.pending == {}


def test_polling_continues_while_job_unfinished() -> None:
    scheduler, threads, events = build()
    runner = make_runner(scheduler, threads)
    runner.submit(lambda report: 1, events.append, events.append)
    scheduler.fire_all()
    assert len(scheduler.pending) == 1
    assert events == []


def test_close_cancels_poll_and_drops_results() -> None:
    scheduler, threads, events = build()
    runner = make_runner(scheduler, threads)
    runner.submit(lambda report: 1, events.append, events.append)
    runner.close()
    threads.run_all()
    scheduler.fire_all()
    assert events == []
    assert scheduler.cancelled


def test_submit_after_close_does_nothing() -> None:
    scheduler, threads, events = build()
    runner = make_runner(scheduler, threads)
    runner.close()
    runner.submit(lambda report: 1, events.append, events.append)
    assert threads.targets == []
