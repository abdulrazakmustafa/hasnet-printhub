from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db
from app.models.alert import Alert
from app.models.device import Device
from app.models.enums import AlertStatus, JobStatus
from app.models.print_job import PrintJob
from app.services.payment_gateway import sync_pending_payments

router = APIRouter()


@router.get("/devices")
def admin_devices(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, object | None]]]:
    query = select(Device).order_by(Device.last_seen_at.desc().nullslast(), Device.created_at.desc())
    if not include_inactive:
        query = query.where(Device.is_active.is_(True))

    devices = db.execute(query).scalars().all()
    items: list[dict[str, object | None]] = []

    for device in devices:
        job_counts_row = db.execute(
            select(
                func.count(PrintJob.id).label("total_jobs"),
                func.sum(case((PrintJob.status == JobStatus.awaiting_payment, 1), else_=0)).label("awaiting_payment"),
                func.sum(
                    case(
                        (
                            PrintJob.status.in_([JobStatus.paid, JobStatus.queued, JobStatus.dispatched, JobStatus.printing]),
                            1,
                        ),
                        else_=0,
                    )
                ).label("in_progress"),
                func.sum(case((PrintJob.status == JobStatus.printed, 1), else_=0)).label("printed"),
                func.sum(case((PrintJob.status == JobStatus.failed, 1), else_=0)).label("failed"),
            ).where(PrintJob.device_id == device.id)
        ).one()

        active_alerts = (
            db.execute(
                select(func.count(Alert.id)).where(
                    Alert.device_id == device.id,
                    Alert.status == AlertStatus.active,
                )
            ).scalar_one()
            or 0
        )

        items.append(
            {
                "device_code": device.device_code,
                "site_name": device.site_name,
                "status": device.status.value,
                "printer_status": device.printer_status.value,
                "is_active": device.is_active,
                "last_seen_at": device.last_seen_at,
                "local_ip": device.local_ip,
                "public_ip": device.public_ip,
                "agent_version": device.agent_version,
                "firmware_version": device.firmware_version,
                "active_alerts": int(active_alerts),
                "jobs": {
                    "total": int(job_counts_row.total_jobs or 0),
                    "awaiting_payment": int(job_counts_row.awaiting_payment or 0),
                    "in_progress": int(job_counts_row.in_progress or 0),
                    "printed": int(job_counts_row.printed or 0),
                    "failed": int(job_counts_row.failed or 0),
                },
            }
        )

    return {"items": items}


@router.post("/payments/reconcile")
def admin_reconcile_payments(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    synced = sync_pending_payments(db, limit=limit)
    return {"status": "ok", "synced": synced, "limit": limit}
