from app.core.security import get_password_hash, verify_password


def test_password_hash_defaults_to_pbkdf2() -> None:
    password = "print-hub-super-admin"
    hashed = get_password_hash(password)
    assert hashed.startswith("$pbkdf2-sha256$")
    assert verify_password(password, hashed) is True


def test_password_hash_supports_long_passwords() -> None:
    password = "A" * 120
    hashed = get_password_hash(password)
    assert verify_password(password, hashed) is True
