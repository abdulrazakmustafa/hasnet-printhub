import os


# Keep test imports deterministic even if local .env is missing.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
