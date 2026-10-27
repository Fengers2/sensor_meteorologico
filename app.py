import json
import logging
import math
import os
import threading
from datetime import datetime, timezone

import serial
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, Table, literal, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import URL

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
db = SQLAlchemy()


def measurement_schema(app):
    """Reflect the existing table and resolve common Spanish/English column names."""
    if "measurement_schema" in app.extensions:
        return app.extensions["measurement_schema"]

    table = Table("mediciones", MetaData(), autoload_with=db.engine)
    actual_columns = {column.name.casefold(): column for column in table.columns}

    def resolve(config_key, candidates, label):
        configured_name = app.config.get(config_key)
        names = [configured_name] if configured_name else candidates
        for name in names:
            if name and name.casefold() in actual_columns:
                return actual_columns[name.casefold()]
        expected = configured_name or " / ".join(candidates)
        raise RuntimeError(
            f"La tabla mediciones no contiene una columna reconocida para {label} ({expected})."
        )

    columns = {
        "temperature": resolve(
            "DB_TEMPERATURE_COLUMN",
            ("temperature", "temperatura", "temp", "temperatura_c"),
            "temperatura",
        ),
        "humidity": resolve(
            "DB_HUMIDITY_COLUMN",
            ("humidity", "humedad", "humedad_relativa"),
            "humedad",
        ),
        "recorded_at": resolve(
            "DB_TIMESTAMP_COLUMN",
            ("recorded_at", "fecha_hora", "fecha_medicion", "timestamp", "created_at", "fecha", "date"),
            "fecha y hora",
        ),
    }
    columns["id"] = next(
        (actual_columns[name] for name in ("id", "id_medicion", "medicion_id") if name in actual_columns),
        None,
    )
    schema = (table, columns)
    app.extensions["measurement_schema"] = schema
    return schema


def serialize_timestamp(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if value is not None and hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise ValueError("La tabla mediciones contiene una fecha vacía o inválida.")


class SerialReader:
    def __init__(self, app):
        self.app = app
        self.stop_event = threading.Event()
        self.thread = None
        self._lock = threading.Lock()
        self._status = {
            "connected": False,
            "message": "Esperando conexión serial",
            "last_seen": None,
            "database_error": None,
        }

    def status(self):
        with self._lock:
            return dict(self._status)

    def _set_status(self, **changes):
        with self._lock:
            self._status.update(changes)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="serial-reader", daemon=True)
        self.thread.start()

    def _run(self):
        port = self.app.config["SERIAL_PORT"]
        baudrate = self.app.config["SERIAL_BAUDRATE"]
        retry_seconds = self.app.config["SERIAL_RECONNECT_SECONDS"]
        while not self.stop_event.is_set():
            try:
                with serial.Serial(port, baudrate, timeout=self.app.config["SERIAL_TIMEOUT"]) as connection:
                    self._set_status(connected=True, message=f"Conectado a {port}")
                    logger.info("Conectado al puerto serial %s a %s baudios", port, baudrate)
                    while not self.stop_event.is_set():
                        raw_line = connection.readline()
                        if not raw_line:
                            continue
                        self._save_line(raw_line)
            except (serial.SerialException, OSError) as exc:
                self._set_status(connected=False, message=f"Sin conexión: {exc}")
                logger.warning("Puerto serial no disponible (%s); reintentando", exc)
            except Exception:
                self._set_status(connected=False, message="Error interno en la lectura serial")
                logger.exception("Error inesperado en el lector serial")
            self.stop_event.wait(retry_seconds)

    def _save_line(self, raw_line):
        try:
            payload = json.loads(raw_line.decode("utf-8").strip())
            temperature = float(payload["temperature"])
            humidity = float(payload["humidity"])
            if not math.isfinite(temperature) or not math.isfinite(humidity) or not 0 <= humidity <= 100:
                raise ValueError("temperatura o humedad fuera de rango")
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Lectura serial ignorada (%s): %r", exc, raw_line[:120])
            return

        try:
            with self.app.app_context():
                table, columns = measurement_schema(self.app)
                values = {
                    columns["temperature"]: temperature,
                    columns["humidity"]: humidity,
                    columns["recorded_at"]: datetime.now(timezone.utc).replace(tzinfo=None),
                }
                with db.engine.begin() as connection:
                    connection.execute(table.insert().values(values))
            self._set_status(last_seen=datetime.now(timezone.utc).isoformat())
            self._set_status(database_error=None)
        except (SQLAlchemyError, RuntimeError) as exc:
            self._set_status(database_error=str(exc))
            logger.exception("No se pudo guardar la medición en MySQL")


def create_app(test_config=None):
    app = Flask(__name__)
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    name = os.getenv("DB_NAME", "Engers_meteorologico")
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=URL.create(
            "mysql+pymysql",
            username=user or None,
            password=password or None,
            host=host,
            port=int(port),
            database=name,
            query={"charset": "utf8mb4"},
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        DB_TEMPERATURE_COLUMN=os.getenv("DB_TEMPERATURE_COLUMN"),
        DB_HUMIDITY_COLUMN=os.getenv("DB_HUMIDITY_COLUMN"),
        DB_TIMESTAMP_COLUMN=os.getenv("DB_TIMESTAMP_COLUMN"),
        SERIAL_PORT=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"),
        SERIAL_BAUDRATE=int(os.getenv("SERIAL_BAUDRATE", "9600")),
        SERIAL_TIMEOUT=float(os.getenv("SERIAL_TIMEOUT", "1")),
        SERIAL_RECONNECT_SECONDS=float(os.getenv("SERIAL_RECONNECT_SECONDS", "3")),
        HISTORY_LIMIT=int(os.getenv("HISTORY_LIMIT", "500")),
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    reader = SerialReader(app)
    app.extensions["serial_reader"] = reader

    @app.get("/")
    def dashboard():
        return render_template("index.html")

    @app.get("/api/measurements")
    def measurements():
        limit = request.args.get("limit", app.config["HISTORY_LIMIT"], type=int)
        limit = min(max(limit or app.config["HISTORY_LIMIT"], 1), 5000)
        try:
            table, columns = measurement_schema(app)
            id_column = columns["id"] if columns["id"] is not None else literal(None)
            statement = (
                select(
                    id_column.label("id"),
                    columns["temperature"].label("temperature"),
                    columns["humidity"].label("humidity"),
                    columns["recorded_at"].label("recorded_at"),
                )
                .select_from(table)
                .order_by(columns["recorded_at"].desc())
                .limit(limit)
            )
            with db.engine.connect() as connection:
                rows = connection.execute(statement).mappings().all()
            return jsonify([
                {
                    "id": row["id"],
                    "temperature": float(row["temperature"]),
                    "humidity": float(row["humidity"]),
                    "recorded_at": serialize_timestamp(row["recorded_at"]),
                }
                for row in reversed(rows)
            ])
        except (SQLAlchemyError, RuntimeError, AttributeError, TypeError, ValueError) as exc:
            logger.exception("No se pudieron consultar las mediciones")
            return jsonify({"error": f"No se pudieron consultar las mediciones: {exc}"}), 503

    @app.get("/api/status")
    def serial_status():
        try:
            measurement_schema(app)
            with db.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            database_status = {"connected": True, "message": "MySQL conectado"}
        except (SQLAlchemyError, RuntimeError) as exc:
            logger.warning("MySQL no disponible: %s", exc)
            database_status = {"connected": False, "message": "MySQL no disponible o tabla mediciones inválida"}
        return jsonify({"serial": reader.status(), "database": database_status})

    return app


app = create_app()

if __name__ == "__main__":
    app.extensions["serial_reader"].start()
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=False,
        use_reloader=False,
    )
