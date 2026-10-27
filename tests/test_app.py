import unittest
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, Table

from app import create_app, db


class MeasurementRoutesTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SERIAL_PORT": "unused-in-test",
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            metadata = MetaData()
            self.table = Table(
                "mediciones",
                metadata,
                Column("id_medicion", Integer, primary_key=True),
                Column("temperatura", Float, nullable=False),
                Column("humedad", Float, nullable=False),
                Column("fecha_hora", DateTime, nullable=False),
            )
            metadata.create_all(db.engine)

    def tearDown(self):
        with self.app.app_context():
            db.engine.dispose()

    def test_serial_reading_is_inserted_and_returned(self):
        reader = self.app.extensions["serial_reader"]
        reader._save_line(b'{"temperature":23.7,"humidity":48.2}\n')

        response = self.client.get("/api/measurements")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["temperature"], 23.7)
        self.assertAlmostEqual(rows[0]["humidity"], 48.2)
        self.assertTrue(rows[0]["recorded_at"].startswith(datetime.now().date().isoformat()))
        self.assertIsNone(reader.status()["database_error"])

    def test_dashboard_and_database_status_are_available(self):
        page = self.client.get("/")
        status = self.client.get("/api/status")

        self.assertEqual(page.status_code, 200)
        self.assertIn("Evolución en el tiempo".encode(), page.data)
        self.assertTrue(status.get_json()["database"]["connected"])

    def test_malformed_serial_row_is_ignored(self):
        reader = self.app.extensions["serial_reader"]
        reader._save_line(b"not-json\n")

        response = self.client.get("/api/measurements")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_missing_table_returns_actionable_api_error(self):
        with self.app.app_context():
            self.table.drop(db.engine)

        response = self.client.get("/api/measurements")

        self.assertEqual(response.status_code, 503)
        self.assertIn("mediciones", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
