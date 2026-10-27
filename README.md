# Monitor ambiental serial

Aplicación local para recibir temperatura y humedad desde un puerto serial, guardarlas en MySQL y consultar el histórico en un panel web con tabla y gráfico.

## Requisitos

- Python 3.10 o posterior.
- Docker Compose para iniciar MySQL (o una instancia MySQL 8 compatible).
- El sensor conectado a un puerto serial reconocido por el sistema.

## Puesta en marcha

1. Crear y activar un entorno virtual de Python.
2. Instalar dependencias desde `requirements.txt`.
3. Copiar `.env.example` a `.env` y configurar `SERIAL_PORT`, baudios y credenciales de MySQL. Ejemplos habituales en Linux: `/dev/ttyUSB0` o `/dev/ttyACM0`.
4. Iniciar la base de datos con Docker Compose usando `compose.yaml` y esperar a que el servicio MySQL indique que está saludable.
5. Ejecutar `python app.py` desde el directorio del proyecto.
6. Abrir `http://127.0.0.1:5000` en el navegador.

La aplicación crea automáticamente la tabla de mediciones al arrancar. MySQL persiste los datos en un volumen Docker llamado `mysql_data`. Si MySQL se ejecuta fuera de Docker, actualizar `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` y `DB_PASSWORD` en `.env`; crear previamente la base de datos y el usuario configurados.

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
| `DB_NAME` | `environment_monitor` | Base de datos |
| `DB_USER` / `DB_PASSWORD` | `monitor` / `change-me` | Credenciales MySQL |
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
