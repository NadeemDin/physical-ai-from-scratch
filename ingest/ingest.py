"""Ingest service. Stores rig readings from MQTT in TimescaleDB.

How it runs:
1. Load the settings from .env.
2. Connect to the database. Keep the connection open.
3. Connect to the MQTT broker.
4. When connected, subscribe to rig/+/features.
5. For each message:
   a. Get the fan ID from the topic.
   b. Find its equipment_id. Skip unknown fans.
   c. Insert one row into readings.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg
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
mqtt_port = int(os.getenv("MQTT_PORT", "1883"))

print("database:", db_name)
print("user:", db_user)
print("mqtt host:", mqtt_host)
print("password set:", bool(db_password))

# One long-lived connection. autocommit saves each INSERT immediately.
conn = psycopg.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    autocommit=True,
)
print("database connected")


def on_connect(client, userdata, flags, reason_code, properties):  # paho passes all five arguments, even unused ones
    print("MQTT connected:", reason_code)
    # Subscribing here means the subscription is renewed after every reconnect.
    client.subscribe("rig/+/features")  # + = any fan


# mqtt_id -> equipment_id, so the database is queried once per fan
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


def on_message(client, userdata, msg):
    mqtt_id = msg.topic.split("/")[1]  # "rig/fan1/features" -> ["rig", "fan1", "features"][1] -> "fan1"
    data = json.loads(msg.payload)

    equipment_id = get_equipment_id(mqtt_id)
    if equipment_id is None:
        print("unknown equipment:", mqtt_id)
        return

    conn.execute(
        "INSERT INTO readings (time, equipment_id, duty, rpm) VALUES (%s, %s, %s, %s)",
        (datetime.now(timezone.utc), equipment_id, data.get("duty"), data.get("rpm")),
    )
    print("stored:", mqtt_id, data.get("duty"), data.get("rpm"))


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingest")
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_host, mqtt_port)
client.loop_forever()