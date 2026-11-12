"""Ingest service. Stores rig readings from MQTT in TimescaleDB.

How it runs:
1. Load the settings from .env.
2. Connect to the database. Keep the connection open.
3. Connect to the MQTT broker.
4. When connected, subscribe to rig/+/features.
5. For each message:
   a. Get the fan ID from the topic.
   b. Find its equipment_id. Skip unknown fans.
   c. Insert one row into readings: every mapped field plus the raw payload.
"""

import json
import os
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

db_name = os.environ["POSTGRES_DB"]
db_user = os.environ["POSTGRES_USER"]
db_password = os.environ["POSTGRES_PASSWORD"]

# Defaults to the local Docker containers. Set these in .env for a cloud database or broker.
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = int(os.getenv("POSTGRES_PORT", "5432"))
mqtt_host = os.getenv("MQTT_HOST", "localhost")
mqtt_port = int(os.getenv("MQTT_PORT", "1883"))  # int(): environment values are always text

print("database:", db_name)
print("user:", db_user)
print("mqtt host:", mqtt_host)
# Never print the password itself, only whether it is set.
print("password set:", bool(db_password))

# One long-lived connection, so on_message can use it.
# autocommit saves each INSERT immediately. Without it, nothing is saved until conn.commit().
conn = psycopg.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    autocommit=True,
)
print("database connected")


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

# Built once at startup from COLUMNS, so a new column is a one-line change.
# Only column names from this file go into the SQL text; values are sent as %s parameters.
cols = ["time", "equipment_id", *COLUMNS.values(), "payload"]
placeholders = ", ".join(["%s"] * len(cols))

INSERT_READING_SQL = f"INSERT INTO readings ({', '.join(cols)}) VALUES ({placeholders})"
INSERT_REJECT_SQL = ("INSERT INTO rejected_messages (topic, raw, error_type, error_message) " 
                     "VALUES (%s, %s, %s, %s)"
                     )


def on_connect(client, userdata, flags, reason_code, properties):  # paho passes all five arguments, even unused ones
    """Subscribe to every fan's readings. paho calls this each time the broker accepts the connection."""
    print("MQTT connected:", reason_code)
    # Subscribing here means the subscription is renewed after every reconnect.
    client.subscribe("rig/+/features")  # + = any fan


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
    conn.execute(INSERT_REJECT_SQL, (msg.topic, raw, error_type, error_message))
    print(f"rejected: {error_type} on {msg.topic}: {error_message}")


def on_message(client, userdata, msg):
    """Store one reading. paho calls this for each message on rig/+/features."""
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
        print(f"warning: payload missing {missing}")

    # Ingest time, not ESP32 time: the ESP32 has no real clock, only uptime_ms.
    ts = datetime.now(timezone.utc)
    # Order must match cols. The full payload is kept so fields without a column are not lost.
    values = [ts, equipment_id, *(data.get(k) for k in COLUMNS), Jsonb(data)]
    try:
        conn.execute(INSERT_READING_SQL, values)
    except psycopg.DataError as e:
        reject(msg, type(e).__name__, str(e))
        return
    print("stored:", mqtt_id, " ".join(f"{k}={data.get(k)}" for k in COLUMNS))


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingest")
# No brackets: paho gets the function itself and calls it later.
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_host, mqtt_port)
# Waits for messages and never returns. paho calls on_connect and on_message from inside it. Stop with Ctrl+C.
client.loop_forever()