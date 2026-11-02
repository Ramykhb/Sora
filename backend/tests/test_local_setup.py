from pathlib import Path

from scripts.configure_local import configure, values


def test_local_setup_generates_secrets_and_preserves_credentials(tmp_path):
    backend, mobile = tmp_path / "backend", tmp_path / "mobile"
    backend.mkdir()
    mobile.mkdir()
    template = Path(__file__).resolve().parents[1] / ".env.example"
    (backend / ".env.example").write_text(template.read_text())
    configure(tmp_path, "192.168.0.102")
    first = values((backend / ".env").read_text())
    assert len(first["POSTGRES_PASSWORD"]) >= 32
    assert "GENERATE_LOCAL_SECRET" not in (backend / ".env").read_text()
    configure(tmp_path, "192.168.0.103")
    second = values((backend / ".env").read_text())
    assert second["POSTGRES_PASSWORD"] == first["POSTGRES_PASSWORD"]
    assert second["DATABASE_URL"] == first["DATABASE_URL"]
    assert second["TURN_PUBLIC_HOST"] == "192.168.0.103"
    assert "http://192.168.0.103:8000" in (mobile / ".env.local").read_text()


def test_template_placeholders_are_replaced_when_user_copied_example(tmp_path):
    backend, mobile = tmp_path / "backend", tmp_path / "mobile"
    backend.mkdir()
    mobile.mkdir()
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    (backend / ".env.example").write_text(example)
    (backend / ".env").write_text(example)
    configure(tmp_path, "192.168.0.102")
    assert "GENERATE_LOCAL_SECRET" not in (backend / ".env").read_text()
