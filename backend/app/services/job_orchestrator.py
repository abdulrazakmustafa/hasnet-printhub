from app.models.enums import JobStatus


def next_job_status(current: JobStatus, payment_confirmed: bool) -> JobStatus:
    if current == JobStatus.awaiting_payment and payment_confirmed:
        return JobStatus.paid
    if current == JobStatus.paid:
        return JobStatus.queued
    if current == JobStatus.queued:
        return JobStatus.dispatched
    return current

