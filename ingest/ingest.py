"""Ingest service. Stores rig readings from MQTT in TimescaleDB.

How it runs:
1. Load the settings from .env.
2. Connect to the database. Keep the connection open.
3. Connect to the MQTT broker.
4. When connected, subscribe to rig/+/features.
5. For each message:
   a. Check it: valid JSON, a JSON object, from known equipment.
   b. Insert one row into readings: every mapped field plus the raw payload.
   c. If a check or the insert fails, store the message in rejected_messages instead.

If the database goes down, messages are dropped and counted, and the service
reconnects every few seconds. It never waits, so stored timestamps stay correct.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

# Load the repo-root .env explicitly, so a .env elsewhere is never picked up by mistake.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if not ENV_FILE.exists():
    raise SystemExit(f"Missing {ENV_FILE}. Copy .env.example to .env and fill it in.")
load_dotenv(ENV_FILE)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL","INFO"),
    format="%(asctime)s %(levelname)-7s %(message)s",
)
log = logging.getLogger("ingest")

db_name = os.environ["POSTGRES_DB"]
db_user = os.environ["POSTGRES_USER"]
db_password = os.environ["POSTGRES_PASSWORD"]

# Defaults to the local Docker containers. Set these in .env for a cloud database or broker.
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = int(os.getenv("POSTGRES_PORT", "5432"))
mqtt_host = os.getenv("MQTT_HOST", "localhost")
mqtt_port = int(os.getenv("MQTT_PORT", "1883"))  # int(): environment values are always text

log.info("database: %s, user: %s, mqtt host: %s", db_name, db_user, mqtt_host)
# Never log the password itself, only whether it is set.
log.info("password set: %s", bool(db_password))


def connect_db():
    """Open a database connection. Used at startup and to reconnect after an outage."""
    # autocommit saves each INSERT immediately, so one failed insert never blocks the next.
    # connect_timeout stops a reconnect attempt from waiting long while the database is down.
    return psycopg.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    autocommit=True,
    connect_timeout =3,
)


conn = connect_db()
log.info("database connected")


# Outage state, shared between messages. db_down_since is None while the database is up.
RECONNECT_INTERVAL_S = 5
db_down_since = None
lost_messages = 0
next_reconnect_at = 0.0


# Payload key -> readings column. Explicit so firmware and schema can rename independently.
COLUMNS = {
    "uptime_ms": "uptime_ms",
    "duty": "duty",
    "rpm": "rpm",
    "current_ma": "current_ma",
    "bus_v": "bus_v",
    "hub_c": "hub_c",
    "airflow_c": "airflow_c",
    "rh": "rh",
    "ax_rms": "ax_rms",
    "ay_rms": "ay_rms",
    "az_rms": "az_rms",
    "a_peak": "a_peak",
    "vib_samples": "vib_samples",
    "power_samples": "power_samples",
}

def build_insert(table, columns):
    """Build a parameterised INSERT with one %s per column. Names come from this file only."""
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"


# Built from COLUMNS, so a new reading field is a one-line change.
READING_COLS = ["time", "equipment_id", *COLUMNS.values(), "payload"]


REJECT_COLS = ["topic", "raw", "raw_bytes", "error_type", "error_message"]


INSERT_READING_SQL = build_insert("readings", READING_COLS)
INSERT_REJECT_SQL = build_insert("rejected_messages", REJECT_COLS)


def on_connect(client, userdata, flags, reason_code, properties):  # paho passes all five arguments, even unused ones
    """Subscribe to every fan's readings. paho calls this each time the broker accepts the connection."""
    log.info("MQTT connected: %s", reason_code)
    # Subscribing here means the subscription is renewed after every reconnect.
    client.subscribe("rig/+/features")  # + = any fan


def on_disconnect(client, userdata, flags, reason_code, properties):
    """Log a lost broker connection. paho keeps trying to reconnect by itself."""
    log.warning("MQTT disconnected: %s", reason_code)
    

def on_connect_fail(client, userdata):
    """Log a failed connection attempt, paho retries by itself, with a growing delay"""
    log. warning("MQTT connection failed, retrying")
        

# mqtt_id -> equipment_id, so the database is queried once per fan.
equipment_ids = {}


def get_equipment_id(mqtt_id):
    """Return the equipment_id for an MQTT id such as 'fan1', or None if it is unknown."""
    if mqtt_id in equipment_ids:
        return equipment_ids[mqtt_id]

    row = conn.execute(
        "SELECT equipment_id FROM equipment WHERE mqtt_id = %s",
        (mqtt_id,),
    ).fetchone()
    # Unknown ids are not cached, so a fan added to the table later is found on its next message.
    if row is None:
        return None

    # Store it, so the next call skips the query.
    equipment_ids[mqtt_id] = row[0]
    return row[0]


def reject(msg, error_type, error_message):
    """Store a message that could not be injested, so transmission faults stay countable."""
    raw = msg.payload.decode("utf-8", errors="backslashreplace")
    conn.execute(INSERT_REJECT_SQL, (msg.topic, raw, msg.payload, error_type, error_message))
    log.warning("rejected: %s on %s: %s" ,error_type, msg.topic, error_message)


def handle_message(msg):
    """Check one message and store it in readings, or reject it."""
    mqtt_id = msg.topic.split("/")[1]  # "rig/fan1/features" -> ["rig", "fan1", "features"][1] -> "fan1"
    try:
        data = json.loads(msg.payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        reject(msg, type(e).__name__, str(e))
        return
    if not isinstance(data,dict):
        reject(msg, "NotAnObject", f"expected a JSON object, got {type(data).__name__}")
        return

    equipment_id = get_equipment_id(mqtt_id)
    if equipment_id is None:
        reject(msg, "UnknownEquipment", f"no equipment with mqtt_id {mqtt_id}")
        return

    # A missing key would become a silent NULL; warn so a firmware change is noticed.
    missing = [k for k in COLUMNS if k not in data]
    if missing:
        log.warning("payload missing %s", missing)

    # Ingest time, not ESP32 time: the ESP32 has no real clock, only uptime_ms.
    ts = datetime.now(timezone.utc)
    # Order must match cols. The full payload is kept so fields without a column are not lost.
    values = [ts, equipment_id, *(data.get(k) for k in COLUMNS), Jsonb(data)]
    try:
        conn.execute(INSERT_READING_SQL, values)
    except psycopg.DataError as e:
        reject(msg, type(e).__name__, str(e))
        return
    log.debug("stored %s: %s", mqtt_id, data)
    
def on_message(client, userdata, msg):
    """Called by paho for each message. A database outage drops the message instead of crashing."""    
    global conn, db_down_since, lost_messages, next_reconnect_at
    if db_down_since is not None:
        if time.monotonic() < next_reconnect_at:
            lost_messages += 1
            return
        try:
            conn = connect_db()
        except psycopg.OperationalError:
            lost_messages += 1
            next_reconnect_at = time.monotonic() + RECONNECT_INTERVAL_S
            return
        log.info("database back after %.0f s, %d messages lost", time.monotonic() - db_down_since, lost_messages)
        db_down_since = None
        lost_messages = 0
    try:
        handle_message(msg)
    except psycopg.OperationalError as e:
        log.error("database connection lost: %s: %s", type(e).__name__, e)
        db_down_since = time.monotonic()
        lost_messages = 1
        next_reconnect_at = db_down_since + RECONNECT_INTERVAL_S


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingest")
# No brackets: paho gets the function itself and calls it later.
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect
client.on_connect_fail = on_connect_fail
client.reconnect_delay_set(min_delay=1, max_delay=30)
# connect_async + retry_first_connection: a broker that is down at startup is retried, not fatal.
client.connect_async(mqtt_host, mqtt_port)
client.loop_forever(retry_first_connection=True)