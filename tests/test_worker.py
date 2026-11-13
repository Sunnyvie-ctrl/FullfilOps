import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from api.models import Order, OutboxJob
from worker import worker as w


@pytest.fixture
def factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def make_jobs(factory, n=1):
    ids = []
    with factory() as s:
        for _ in range(n):
            order = Order(
                idempotency_key=str(uuid.uuid4()),
                payload_hash="h" * 64,
                customer_id="cust-1",
                total_cents=100,
            )
            s.add(order)
            s.flush()

            job = OutboxJob(order_id=order.id)
            s.add(job)
            s.flush()
            ids.append(job.id)

        s.commit()

    return ids


def get_job(factory, job_id):
    with factory() as s:
        return s.get(OutboxJob, job_id)


def get_order_status(factory, order_id):
    with factory() as s:
        return s.get(Order, order_id).status


def boom(session, job):
    raise RuntimeError("nope")


def test_success_marks_done_and_completes_order(factory):
    (jid,) = make_jobs(factory)

    assert w.run_once(factory, "w1") == 1

    job = get_job(factory, jid)
    assert job.status == "done"
    assert job.attempts == 1
    assert get_order_status(factory, job.order_id) == "completed"


def test_claim_marks_order_processing(factory):
    (jid,) = make_jobs(factory)

    with factory() as s:
        job = s.get(OutboxJob, jid)
        order_id = job.order_id

    with factory() as s:
        claimed = w.claim_jobs(s, "w1")
        assert len(claimed) == 1

    job = get_job(factory, jid)
    assert job.status == "processing"
    assert job.attempts == 1
    assert get_order_status(factory, order_id) == "processing"


def test_done_job_is_not_processed_again(factory):
    make_jobs(factory)

    assert w.run_once(factory, "w1") == 1
    assert w.run_once(factory, "w1") == 0


def test_failure_goes_back_to_pending_with_backoff(factory):
    (jid,) = make_jobs(factory)

    w.run_once(factory, "w1", handler=boom)

    job = get_job(factory, jid)
    assert job.status == "pending"
    assert job.attempts == 1
    assert get_order_status(factory, job.order_id) == "processing"

    assert w.run_once(factory, "w1", handler=boom) == 0


def test_retry_happens_after_backoff(factory, monkeypatch):
    monkeypatch.setattr(w, "BACKOFF_BASE", 0.0)

    (jid,) = make_jobs(factory)
    w.run_once(factory, "w1", handler=boom)

    assert w.run_once(factory, "w1") == 1

    job = get_job(factory, jid)
    assert job.status == "done"
    assert get_order_status(factory, job.order_id) == "completed"


def test_dead_letter_after_max_attempts(factory, monkeypatch):
    monkeypatch.setattr(w, "MAX_ATTEMPTS", 3)
    monkeypatch.setattr(w, "BACKOFF_BASE", 0.0)

    (jid,) = make_jobs(factory)

    for _ in range(3):
        w.run_once(factory, "w1", handler=boom)

    job = get_job(factory, jid)
    assert job.status == "dead"
    assert job.attempts == 3
    assert get_order_status(factory, job.order_id) == "failed"
    assert w.run_once(factory, "w1") == 0


def test_stale_job_exhausting_attempts_marks_order_failed(factory, monkeypatch):
    monkeypatch.setattr(w, "MAX_ATTEMPTS", 3)

    (jid,) = make_jobs(factory)

    with factory() as s:
        job = s.get(OutboxJob, jid)
        order_id = job.order_id
        job.status = "processing"
        job.attempts = 3
        job.updated_at = w.utcnow() - timedelta(seconds=w.VISIBILITY_TIMEOUT + 5)
        s.commit()

    with factory() as s:
        claimed = w.claim_jobs(s, "w2")
        assert claimed == []

    job = get_job(factory, jid)
    assert job.status == "dead"
    assert job.attempts == 3
    assert get_order_status(factory, order_id) == "failed"


def test_backoff_grows_and_is_capped():
    assert w.backoff_seconds(2) == 2 * w.backoff_seconds(1)
    assert w.backoff_seconds(50) == w.BACKOFF_CAP


def test_crashed_worker_job_is_reclaimed(factory):
    (jid,) = make_jobs(factory)

    with factory() as s:
        job = s.get(OutboxJob, jid)
        job.status = "processing"
        job.attempts = 1
        job.updated_at = w.utcnow() - timedelta(seconds=w.VISIBILITY_TIMEOUT + 5)
        s.commit()

    assert w.run_once(factory, "w2") == 1
    assert get_job(factory, jid).status == "done"


def test_fresh_processing_job_is_left_alone(factory):
    (jid,) = make_jobs(factory)

    with factory() as s:
        job = s.get(OutboxJob, jid)
        job.status = "processing"
        job.attempts = 1
        s.commit()

    assert w.run_once(factory, "w2") == 0


def test_concurrent_workers_never_double_claim(factory):
    ids = make_jobs(factory, n=40)

    def work(name):
        got = []

        while True:
            with factory() as s:
                jobs = w.claim_jobs(s, name, batch_size=5)

            if not jobs:
                return got

            got += [job.id for job in jobs]

    claimed = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(work, [f"w{i}" for i in range(4)]):
            claimed += result

    assert len(claimed) == len(set(claimed))
    assert sorted(claimed) == sorted(ids)
