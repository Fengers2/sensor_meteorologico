# sensor_meteorologico

## Monitor ambiental serial

Aplicación local para recibir temperatura y humedad desde un puerto serial, guardarlas en MySQL y consultar el histórico en un panel web con tabla y gráfico.

## Requisitos

- Python 3.10 o posterior.
- Docker Compose para iniciar MySQL (o una instancia MySQL 8 compatible).
- El sensor conectado a un puerto serial reconocido por el sistema.

## Puesta en marcha

1. Crear y activar un entorno virtual de Python.
2. Instalar dependencias desde `requirements.txt`.
3. Copiar `.env.example` a `.env` y configurar el usuario y contraseña de tu MySQL, además de `SERIAL_PORT` y los baudios. Ejemplos habituales en Linux: `/dev/ttyUSB0` o `/dev/ttyACM0`.
4. Verificar que tu servidor MySQL esté iniciado y que el usuario configurado tenga acceso a `Engers_meteorologico`.
5. Ejecutar `python app.py` desde el directorio del proyecto.
6. Abrir `http://127.0.0.1:5000` en el navegador.

La aplicación consulta e inserta directamente en la tabla existente `Engers_meteorologico.mediciones`; no crea ni modifica tablas. El usuario MySQL necesita permisos de lectura e inserción. La aplicación reconoce nombres comunes en inglés y español, como `temperature`/`temperatura`, `humidity`/`humedad` y `recorded_at`/`fecha_hora`. Si el esquema utiliza otros nombres, indicarlos con `DB_TEMPERATURE_COLUMN`, `DB_HUMIDITY_COLUMN` y `DB_TIMESTAMP_COLUMN` en `.env`.

No iniciar el MySQL de Docker Compose si ya se está usando otro servicio local en el puerto 3306. Compose es solo para una instalación MySQL separada; sus credenciales de ejemplo deben coincidir con las configuradas en `.env`.

> Cambiar las contraseñas de ejemplo antes de usar el sistema en una red compartida. `.env` no se guarda en Git.

## Protocolo serial

El lector espera una línea UTF-8 por medición, terminada en salto de línea, con un objeto JSON que contenga los campos numéricos `temperature` y `humidity`. Por ejemplo, el dispositivo debe transmitir:

```json
{"temperature":23.7,"humidity":48.2}
```

La humedad debe estar entre 0 y 100 %. Las líneas mal formadas o fuera de rango se descartan y quedan registradas en el log; el lector reintenta automáticamente si se desconecta el puerto. Ajustar `SERIAL_BAUDRATE` al valor utilizado por el microcontrolador (9600 por defecto).

En Linux, verificar que el usuario tenga permiso de acceso al puerto serial (normalmente mediante el grupo `dialout`) y volver a iniciar sesión si se cambia la pertenencia al grupo.

Si el dispositivo envía otro formato, adaptar el método `_save_line` de `SerialReader` en `app.py` para analizarlo. El formato de almacenamiento y el dashboard no necesitan cambiar.

## Configuración opcional

| Variable | Predeterminado | Uso |
| --- | --- | --- |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `3306` | Dirección de MySQL |
| `DB_NAME` | `Engers_meteorologico` | Base de datos |
| `DB_USER` / `DB_PASSWORD` | Sin valor | Credenciales de tu instancia MySQL |
| `DB_TEMPERATURE_COLUMN` | Detección automática | Nombre de la columna de temperatura |
| `DB_HUMIDITY_COLUMN` | Detección automática | Nombre de la columna de humedad |
| `DB_TIMESTAMP_COLUMN` | Detección automática | Nombre de la columna de fecha y hora |
| `SERIAL_PORT` | `/dev/ttyUSB0` | Puerto serial |
| `SERIAL_BAUDRATE` | `9600` | Velocidad serial |
| `SERIAL_TIMEOUT` | `1` | Tiempo de lectura serial en segundos |
| `SERIAL_RECONNECT_SECONDS` | `3` | Pausa entre reintentos de conexión |
| `HISTORY_LIMIT` | `500` | Cantidad máxima de muestras devueltas por consulta |
| `FLASK_HOST` / `FLASK_PORT` | `127.0.0.1` / `5000` | Dirección de escucha de la web |

## API local

- `GET /api/measurements?limit=500`: lecturas en orden cronológico.
- `GET /api/status`: estado de conexión serial.

El dashboard consulta estos endpoints cada cinco segundos y muestra las últimas mediciones junto con su evolución temporal.
