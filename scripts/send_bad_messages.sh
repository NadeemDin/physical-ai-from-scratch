#!/bin/sh
# Publish one example of each message the ingest service rejects.
# Run with the broker and ingest service up, then check: SELECT * FROM rejected_messages;
HOST="${MQTT_HOST:-localhost}"

mosquitto_pub -h "$HOST" -t 'rig/fan1/features' -m '{"rpm": 12'          # JSONDecodeError
mosquitto_pub -h "$HOST" -t 'rig/fan1/features' -m '42'                   # NotAnObject
mosquitto_pub -h "$HOST" -t 'rig/fan99/features' -m '{"rpm": 1}'          # UnknownEquipment
mosquitto_pub -h "$HOST" -t 'rig/fan1/features' -m '{"duty": 99999}'      # NumericValueOutOfRange
printf '\xff{"rpm": 12}' | mosquitto_pub -h "$HOST" -t 'rig/fan1/features' -s   # UnicodeDecodeError


#make it runnable and then run it:
#chmod +x scripts/send_bad_messages.sh
#./scripts/send_bad_messages.sh