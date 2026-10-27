import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_fixed_embedding_dimension_can_be_set_through_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
    assert Settings(_env_file=None).embedding_dimensions == 1024
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "2048")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
