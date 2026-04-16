from app.db.base_class import Base


# Alembic auto-discovery imports
from app.models.admin_user import AdminUser  # noqa: E402,F401
from app.models.alert import Alert  # noqa: E402,F401
from app.models.device import Device  # noqa: E402,F401
from app.models.log import LogEntry  # noqa: E402,F401
from app.models.payment import Payment  # noqa: E402,F401
from app.models.pricing_rule import PricingRule  # noqa: E402,F401
from app.models.print_job import PrintJob  # noqa: E402,F401
