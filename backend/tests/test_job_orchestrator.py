from app.models.enums import JobStatus
from app.services.job_orchestrator import next_job_status


def test_awaiting_payment_moves_to_paid_when_confirmed() -> None:
    assert next_job_status(JobStatus.awaiting_payment, payment_confirmed=True) == JobStatus.paid


def test_awaiting_payment_stays_when_not_confirmed() -> None:
    assert next_job_status(JobStatus.awaiting_payment, payment_confirmed=False) == JobStatus.awaiting_payment


def test_paid_moves_to_queued() -> None:
    assert next_job_status(JobStatus.paid, payment_confirmed=True) == JobStatus.queued


def test_queued_moves_to_dispatched() -> None:
    assert next_job_status(JobStatus.queued, payment_confirmed=True) == JobStatus.dispatched


def test_terminal_status_stays_unchanged() -> None:
    assert next_job_status(JobStatus.printed, payment_confirmed=True) == JobStatus.printed
