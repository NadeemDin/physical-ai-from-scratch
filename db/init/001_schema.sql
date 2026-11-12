-- Schema for the fan rig: sites → systems → equipment → readings.
-- The hierarchy follows the public building-data standards Project Haystack and Brick Schema (a small subset).
-- Runs automatically the first time the database starts with an empty volume.


CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE sites (
    site_id      SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT
);

CREATE TABLE systems (
    system_id    SERIAL PRIMARY KEY,
    site_id      INTEGER NOT NULL REFERENCES sites (site_id),
    name         TEXT NOT NULL,
    type         TEXT,            -- e.g. 'ventilation', 'test-rig'
    UNIQUE (site_id, name)
);

CREATE TABLE equipment (
    equipment_id SERIAL PRIMARY KEY,
    system_id    INTEGER NOT NULL REFERENCES systems (system_id),
    mqtt_id      TEXT NOT NULL UNIQUE,          -- matches the MQTT topic: rig/<mqtt_id>/features
    name         TEXT NOT NULL,
    model        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE readings (
    time          TIMESTAMPTZ NOT NULL,         -- set by the ingest service when the message arrives
    equipment_id  INTEGER     NOT NULL REFERENCES equipment (equipment_id),
    uptime_ms     BIGINT,
    duty          SMALLINT,
    rpm           INTEGER,
    current_ma    REAL,
    bus_v         REAL,
    hub_c         REAL,
    airflow_c     REAL,
    rh            REAL,
    ax_rms        REAL,
    ay_rms        REAL,
    az_rms        REAL,
    a_peak        REAL,
    vib_samples   SMALLINT,
    power_samples SMALLINT,
    payload       JSONB       NOT NULL,     -- the original message, so new fields are never lost                        -- the original message, so new fields are never lost
    PRIMARY KEY (equipment_id, time)
);

   -- Messages the ingest service could not store (bad JSON, wrong shape, bad values, unknown equipment).
-- Kept as data, not only logged, so transmission faults can be counted and charted.
CREATE TABLE rejected_messages (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic         TEXT NOT NULL,
    raw           TEXT NOT NULL,           -- decoded with bad bytes escaped, so nothing is lost
    raw_bytes     BYTEA NOT NULL,          -- the exact bytes received, unchanged
    error_type    TEXT NOT NULL,           -- exception name, e.g. JSONDecodeError
    error_message TEXT
);

-- Turn readings into a hypertable, split into one-day chunks
SELECT create_hypertable('readings', by_range('time', INTERVAL '1 day'));

-- The rig itself
INSERT INTO sites (name, description) VALUES ('home-lab', 'Desk rig at home');
INSERT INTO systems (site_id, name, type) VALUES (1, 'rig-1', 'test-rig');
INSERT INTO equipment (system_id, mqtt_id, name, model)
VALUES (1, 'fan1', 'Rig fan 1', 'Arctic P12 Pro');