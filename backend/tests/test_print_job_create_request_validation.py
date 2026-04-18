from pydantic import ValidationError

from app.schemas.print_job import PrintJobCreateRequest


def _base_payload() -> dict:
    return {
        "pages": 5,
        "copies": 1,
        "color": "bw",
        "page_selection": "all",
        "device_code": "pi-kiosk-001",
        "original_file_name": "doc.pdf",
        "storage_key": "https://example.com/test-assets/doc.pdf",
        "bw_price_per_page": 100,
        "color_price_per_page": 300,
        "currency": "TZS",
    }


def test_create_request_normalizes_fields() -> None:
    payload = _base_payload()
    payload["color"] = " COLOR "
    payload["device_code"] = " pi-kiosk-001 "
    payload["original_file_name"] = "  receipt.pdf  "
    payload["storage_key"] = "  https://example.com/print/receipt.pdf  "
    payload["currency"] = "tzs"
    payload["page_selection"] = " RANGE "

    model = PrintJobCreateRequest(**payload)

    assert model.color == "color"
    assert model.device_code == "pi-kiosk-001"
    assert model.original_file_name == "receipt.pdf"
    assert model.storage_key == "https://example.com/print/receipt.pdf"
    assert model.currency == "TZS"
    assert model.page_selection == "range"


def test_create_request_uses_safe_defaults_for_blank_optional_text() -> None:
    payload = _base_payload()
    payload["device_code"] = " "
    payload["original_file_name"] = " "
    payload["storage_key"] = " "

    model = PrintJobCreateRequest(**payload)

    assert model.device_code == "prototype-local"
    assert model.original_file_name == "pending-upload.pdf"
    assert model.storage_key is None


def test_create_request_rejects_invalid_color() -> None:
    payload = _base_payload()
    payload["color"] = "sepia"

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for unsupported color"
    except ValidationError as exc:
        assert "Unsupported color mode" in str(exc)


def test_create_request_rejects_invalid_device_code() -> None:
    payload = _base_payload()
    payload["device_code"] = "bad code"

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for invalid device_code"
    except ValidationError as exc:
        assert "must not contain spaces" in str(exc)


def test_create_request_rejects_original_file_name_with_path_separator() -> None:
    payload = _base_payload()
    payload["original_file_name"] = "folder/doc.pdf"

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for original_file_name path separator"
    except ValidationError as exc:
        assert "must not include path separators" in str(exc)


def test_create_request_rejects_unsafe_storage_key_scheme() -> None:
    payload = _base_payload()
    payload["storage_key"] = "file:///etc/passwd"

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for unsafe storage_key"
    except ValidationError as exc:
        assert "must not use the file:// scheme" in str(exc)


def test_create_request_rejects_storage_key_traversal() -> None:
    payload = _base_payload()
    payload["storage_key"] = "../secret.pdf"

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for storage_key traversal"
    except ValidationError as exc:
        assert "must not contain parent-directory traversal" in str(exc)


def test_create_request_rejects_invalid_currency() -> None:
    payload = _base_payload()
    payload["currency"] = "Tanzania"

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for invalid currency"
    except ValidationError as exc:
        assert "currency must be a 3-letter ISO code" in str(exc)


def test_create_request_rejects_page_count_over_limit() -> None:
    payload = _base_payload()
    payload["pages"] = 2001

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for page upper limit"
    except ValidationError as exc:
        assert "less than or equal to 2000" in str(exc)


def test_create_request_rejects_invalid_page_selection() -> None:
    payload = _base_payload()
    payload["page_selection"] = "chapter"

    try:
        PrintJobCreateRequest(**payload)
        assert False, "Expected ValidationError for invalid page_selection"
    except ValidationError as exc:
        assert "page_selection must be 'all' or 'range'" in str(exc)
