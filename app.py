import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timezone

import serial
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
db = SQLAlchemy()


class Measurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, index=True)


class SerialReader:
    def __init__(self, app):
        self.app = app
        self.stop_event = threading.Event()
        self.thread = None
        self._lock = threading.Lock()
        self._status = {"connected": False, "message": "Esperando conexión serial", "last_seen": None}

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
                measurement = Measurement(
                    temperature=temperature,
                    humidity=humidity,
                    recorded_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                db.session.add(measurement)
                db.session.commit()
            self._set_status(last_seen=datetime.now(timezone.utc).isoformat())
        except SQLAlchemyError:
            with self.app.app_context():
                db.session.rollback()
            logger.exception("No se pudo guardar la medición en MySQL")


def create_app():
    app = Flask(__name__)
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    name = os.getenv("DB_NAME", "environment_monitor")
    user = os.getenv("DB_USER", "monitor")
    password = os.getenv("DB_PASSWORD", "change-me")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SERIAL_PORT=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"),
        SERIAL_BAUDRATE=int(os.getenv("SERIAL_BAUDRATE", "9600")),
        SERIAL_TIMEOUT=float(os.getenv("SERIAL_TIMEOUT", "1")),
        SERIAL_RECONNECT_SECONDS=float(os.getenv("SERIAL_RECONNECT_SECONDS", "3")),
        HISTORY_LIMIT=int(os.getenv("HISTORY_LIMIT", "500")),
    )
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
        rows = Measurement.query.order_by(desc(Measurement.recorded_at)).limit(limit).all()
        rows.reverse()
        return jsonify([
            {"id": row.id, "temperature": row.temperature, "humidity": row.humidity,
             "recorded_at": row.recorded_at.replace(tzinfo=timezone.utc).isoformat()}
            for row in rows
        ])

    @app.get("/api/status")
    def serial_status():
        return jsonify({"serial": reader.status()})

    return app


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.extensions["serial_reader"].start()
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=False,
        use_reloader=False,
    )
