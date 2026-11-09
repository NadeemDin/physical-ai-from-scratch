#imports
import os
#db connection and querying
import psycopg 
#load env
from dotenv import load_dotenv 
#for looping our broker
import paho.mqtt.client as mqtt
#load only the env at repo root
from pathlib import Path 
#setting time
from datetime import datetime, timezone
import json

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if not ENV_FILE.exists():
    raise SystemExit(f"Missing {ENV_FILE}. Copy .env.example to .env and fill it in.")
load_dotenv(ENV_FILE)

#read values / settings
db_name = os.environ["POSTGRES_DB"]
db_user = os.environ["POSTGRES_USER"]
db_password = os.environ["POSTGRES_PASSWORD"]
mqtt_host = os.getenv("MQTT_HOST","localhost") # MQTT_HOST not in env, defaults to localhost

# I will later set these in my .env if i decide to host db on cloud
db_host = os.getenv("POSTGRES_HOST", "localhost")
db_port = int(os.getenv("POSTGRES_PORT", "5432"))

mqtt_port = int(os.getenv("MQTT_PORT", "1883"))

#print

print("database:", db_name)
print("user:", db_user)
print("mqtt host:", mqtt_host)
print("password set:", bool(db_password))


#connecting to DB and querying
# opens connection and calls it conn, indentation closes connection automatically 
conn = psycopg.connect(
    host = db_host,
    port = db_port,
    dbname = db_name,
    user = db_user,
    password = db_password,
    autocommit = True,
)
print("database connected")
    
# connect to broker and print each message

#CALLBACKS

def on_connect(client, userdata, flags, reason_code,properties): #paho requires all five args even if were not using them all
    print("MQTT connected:", reason_code)
    client.subscribe("rig/+/features") #+ means any one level, so every fans readings. currently only one fan.
    

equipment_ids = {}    
    
def get_equipment_id(mqtt_id):
    if mqtt_id in equipment_ids:
        return equipment_ids[mqtt_id]
    print("database lookup for", mqtt_id)
    row = conn.execute(
        "SELECT equipment_id from equipment where mqtt_id = %s",
        (mqtt_id,),
    ).fetchone()
    if row is None:
        return None
    equipment_ids[mqtt_id] = row[0] # store it, so the next call skips the query
    return row[0] #0 is equipment_id
    
def on_message(client, userdata,msg):
    mqtt_id = msg.topic.split("/")[1] # → ["rig", "fan1", "features"][1]
    data = json.loads(msg.payload)
    
    equipment_id = get_equipment_id(mqtt_id)
    if equipment_id is None:
        print("unknown equipment:", mqtt_id)
        return
    
    conn.execute(
        "INSERT INTO readings (time, equipment_id, duty, rpm) VALUES (%s,%s,%s,%s)",
        (datetime.now(timezone.utc), equipment_id, data.get("duty"), data.get("rpm")),
    )
    print("stored:", mqtt_id, data.get("duty"), data.get("rpm"))
    
    print(mqtt_id, "duty:", data["duty"],"rpm:", data["rpm"], "current:", data["current_ma"], "hub temperature:", data["hub_c"]) 
    
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id ="ingest")    
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_host, mqtt_port)
client.loop_forever()