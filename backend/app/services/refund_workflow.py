from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import PaymentStatus
from app.models.log import LogEntry
from app.models.payment import Payment
from app.models.print_job import PrintJob

_REFUND_STORE_PATH = Path(__file__).resolve().parents[2] / "assets" / "refund-workflow.json"

_TERMINAL_REFUND_STATUSES = {"executed", "rejected", "cancelled"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: object, *, default: str = "", max_len: int = 240) -> str:
    text = str(value or "").strip()
    return text[:max_len] if text else default


def _load_refund_store() -> dict[str, Any]:
    if not _REFUND_STORE_PATH.exists():
        return {"requests": []}
    try:
        payload = json.loads(_REFUND_STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"requests": []}
    if not isinstance(payload, dict):
        return {"requests": []}
    requests = payload.get("requests")
    if not isinstance(requests, list):
        return {"requests": []}
    return {"requests": requests}


def _save_refund_store(store: dict[str, Any]) -> None:
    _REFUND_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REFUND_STORE_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def list_refund_requests(*, payment_id: str | None = None, status_filter: str | None = None) -> list[dict[str, Any]]:
    store = _load_refund_store()
    items = deepcopy(store.get("requests", []))
    if payment_id:
        items = [item for item in items if str(item.get("payment_id")) == str(payment_id)]
    if status_filter:
        needle = status_filter.strip().lower()
        items = [item for item in items if str(item.get("status", "")).strip().lower() == needle]
    items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return items


def _find_refund_or_404(store: dict[str, Any], refund_id: str) -> dict[str, Any]:
    for item in store.get("requests", []):
        if str(item.get("refund_id")) == str(refund_id):
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Refund request '{refund_id}' was not found.")


def create_refund_request(
    *,
    db: Session,
    payment_id: str,
    reason: str,
    requested_by: str,
) -> dict[str, Any]:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found.")
    if payment.status != PaymentStatus.confirmed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only confirmed payments can start a refund workflow.",
        )

    store = _load_refund_store()
    open_requests = [
        item
        for item in store.get("requests", [])
        if str(item.get("payment_id")) == str(payment.id) and str(item.get("status")) not in _TERMINAL_REFUND_STATUSES
    ]
    if open_requests:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active refund request already exists for payment {payment.id}.",
        )

    refund_id = str(uuid.uuid4())
    item = {
        "refund_id": refund_id,
        "payment_id": str(payment.id),
        "print_job_id": str(payment.print_job_id),
        "status": "requested",
        "reason": _safe_text(reason, default="No reason provided."),
        "requested_by": _safe_text(requested_by, default="operator"),
        "approved_by": None,
        "executed_by": None,
        "rejected_by": None,
        "note": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "events": [
            {
                "event": "requested",
                "by": _safe_text(requested_by, default="operator"),
                "at": _now_iso(),
                "note": _safe_text(reason, default="No reason provided."),
            }
        ],
    }
    store["requests"].append(item)
    _save_refund_store(store)

    db.add(
        LogEntry(
            device_id=None,
            print_job_id=payment.print_job_id,
            payment_id=payment.id,
            level="warning",
            event_type="refund.requested",
            message="Refund workflow request created.",
            payload={
                "refund_id": refund_id,
                "requested_by": item["requested_by"],
                "reason": item["reason"],
            },
        )
    )
    db.commit()
    return item


def approve_refund_request(
    *,
    db: Session,
    refund_id: str,
    approved_by: str,
    note: str,
) -> dict[str, Any]:
    store = _load_refund_store()
    item = _find_refund_or_404(store, refund_id)
    if item.get("status") != "requested":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only requested refunds can be approved.")

    item["status"] = "approved"
    item["approved_by"] = _safe_text(approved_by, default="operator")
    item["note"] = _safe_text(note, default="")
    item["updated_at"] = _now_iso()
    item.setdefault("events", []).append(
        {
            "event": "approved",
            "by": item["approved_by"],
            "at": _now_iso(),
            "note": item["note"],
        }
    )
    _save_refund_store(store)

    payment = db.get(Payment, item["payment_id"])
    if payment is not None:
        db.add(
            LogEntry(
                device_id=None,
                print_job_id=payment.print_job_id,
                payment_id=payment.id,
                level="warning",
                event_type="refund.approved",
                message="Refund request approved.",
                payload={
                    "refund_id": item["refund_id"],
                    "approved_by": item["approved_by"],
                    "note": item["note"],
                },
            )
        )
        db.commit()
    return item


def reject_refund_request(
    *,
    db: Session,
    refund_id: str,
    rejected_by: str,
    note: str,
) -> dict[str, Any]:
    store = _load_refund_store()
    item = _find_refund_or_404(store, refund_id)
    if str(item.get("status")) in _TERMINAL_REFUND_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Refund request is already finalized.")

    item["status"] = "rejected"
    item["rejected_by"] = _safe_text(rejected_by, default="operator")
    item["note"] = _safe_text(note, default="")
    item["updated_at"] = _now_iso()
    item.setdefault("events", []).append(
        {
            "event": "rejected",
            "by": item["rejected_by"],
            "at": _now_iso(),
            "note": item["note"],
        }
    )
    _save_refund_store(store)

    payment = db.get(Payment, item["payment_id"])
    if payment is not None:
        db.add(
            LogEntry(
                device_id=None,
                print_job_id=payment.print_job_id,
                payment_id=payment.id,
                level="warning",
                event_type="refund.rejected",
                message="Refund request rejected.",
                payload={
                    "refund_id": item["refund_id"],
                    "rejected_by": item["rejected_by"],
                    "note": item["note"],
                },
            )
        )
        db.commit()
    return item


def execute_refund_request(
    *,
    db: Session,
    refund_id: str,
    executed_by: str,
    note: str,
) -> dict[str, Any]:
    store = _load_refund_store()
    item = _find_refund_or_404(store, refund_id)
    if item.get("status") != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved refunds can be executed.")

    payment = db.get(Payment, item["payment_id"])
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Related payment not found.")
    print_job = db.get(PrintJob, payment.print_job_id)

    payment.status = PaymentStatus.refunded
    payload = payment.provider_payload if isinstance(payment.provider_payload, dict) else {}
    payload = dict(payload)
    payload["refund"] = {
        "refund_id": item["refund_id"],
        "executed_by": _safe_text(executed_by, default="operator"),
        "executed_at": _now_iso(),
        "note": _safe_text(note, default=""),
    }
    payment.provider_payload = payload

    if print_job is not None and not print_job.failure_reason:
        print_job.failure_reason = "Refunded after payment workflow."

    item["status"] = "executed"
    item["executed_by"] = _safe_text(executed_by, default="operator")
    item["note"] = _safe_text(note, default="")
    item["updated_at"] = _now_iso()
    item.setdefault("events", []).append(
        {
            "event": "executed",
            "by": item["executed_by"],
            "at": _now_iso(),
            "note": item["note"],
        }
    )
    _save_refund_store(store)

    db.add(
        LogEntry(
            device_id=print_job.device_id if print_job else None,
            print_job_id=print_job.id if print_job else None,
            payment_id=payment.id,
            level="warning",
            event_type="refund.executed",
            message="Refund marked as executed by operator workflow.",
            payload={
                "refund_id": item["refund_id"],
                "executed_by": item["executed_by"],
                "note": item["note"],
            },
        )
    )
    db.commit()
    return item

