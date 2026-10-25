import os

# Tests use no live services or credentials. File-backed engines are allocated per API test.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["STORAGE_BACKEND"] = "local"

os.environ["API_KEY"] = "test-only-key"
os.environ["APP_ENV"] = "test"
