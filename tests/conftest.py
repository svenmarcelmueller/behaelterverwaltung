import pytest

from app import db


@pytest.fixture
def conn(tmp_path):
    pfad = tmp_path / "behaelter.db"
    db.migrieren(pfad)
    verbindung = db.verbinden(pfad)
    yield verbindung
    verbindung.close()
