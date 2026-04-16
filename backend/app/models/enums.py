from enum import Enum


class DeviceStatus(str, Enum):
    online = "online"
    offline = "offline"
    degraded = "degraded"
    maintenance = "maintenance"


class PrinterStatus(str, Enum):
    unknown = "unknown"
    ready = "ready"
    printing = "printing"
    offline = "offline"
    paper_out = "paper_out"
    paused = "paused"
    error = "error"
    queue_stuck = "queue_stuck"
    low_toner = "low_toner"
    paper_jam = "paper_jam"
    cover_open = "cover_open"


class JobStatus(str, Enum):
    created = "created"
    awaiting_payment = "awaiting_payment"
    paid = "paid"
    queued = "queued"
    dispatched = "dispatched"
    printing = "printing"
    printed = "printed"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class ColorMode(str, Enum):
    bw = "bw"
    color = "color"


class PaymentMethod(str, Enum):
    mpesa = "mpesa"
    airtel = "airtel"
    tigo = "tigo"
    snippe = "snippe"


class PaymentStatus(str, Enum):
    initiated = "initiated"
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"
    expired = "expired"
    refunded = "refunded"


class AlertType(str, Enum):
    device_offline = "device_offline"
    device_recovered = "device_recovered"
    printer_offline = "printer_offline"
    paper_out = "paper_out"
    printer_error = "printer_error"
    job_failed = "job_failed"
    queue_stuck = "queue_stuck"


class AlertStatus(str, Enum):
    active = "active"
    resolved = "resolved"


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"

