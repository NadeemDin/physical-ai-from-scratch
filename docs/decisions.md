# Decisions

Each entry records what I chose, why, and what else I considered.

---

## The LLM explains, it never acts (4 Nov 2026)
**Decision:** the LLM only writes explanations. The safety cut-off is hard-coded on the ESP32.
**Why:** safety must be deterministic and work without the network. An LLM can be wrong or slow.
**Alternatives:** let the LLM trigger actions. Not acceptable for a safety function.

## Security basics (6 Nov 2026)
**Decision:** the database port is bound to `127.0.0.1` only. Secrets live in ignored `.env` and `secrets.h` files, with committed example files. All SQL is parameterised.
**Why:** the database is never reachable from the network. Secrets never reach GitHub. Parameterised SQL prevents SQL injection.
**Alternatives:** an open database port (simpler, unsafe). The MQTT broker is open to the Wi-Fi for now, because the ESP32 needs it. A broker password comes later.

## Health states (8 Nov 2026, updated 11 Nov 2026)
**Decision:** Normal, Watch, Fault and Unknown. Resonance is a watch state, not a fault. The health state is worked out from connectivity, operating state and condition. When connectivity is not online, health is Unknown.
**Why:** passing through resonance is normal, staying in it needs attention, and a shift in resonance can be an early sign of a loose mount. With no data, I cannot claim the fan is healthy, so the UI must never show Normal for a fan that is offline.
**Alternatives:** a single healthy/faulty flag. Too coarse to show early warnings, and it has no honest answer when data stops.

## Equipment hierarchy based on Haystack and Brick (9 Nov 2026)
**Decision:** I store equipment as sites → systems → equipment, with readings linked to equipment.
**Why:** this matches how real buildings and plants are organised. It is a small subset of Project Haystack and Brick Schema, so the model can grow from one fan to a fleet or a building without a redesign.
**Alternatives:** one flat readings table with a fan name column. Simpler, but it breaks as soon as there is more than one site or system.

## Integer IDs (9 Nov 2026)
**Decision:** I use integer IDs for sites, systems and equipment.
**Why:** they are small, fast to join and easy to read while debugging. All records are created in one place, so there is no risk of two IDs clashing.
**Alternatives:** UUIDv7. Better when IDs are public or many sites create records independently. I will switch only if that becomes true.

## Readings as a TimescaleDB hypertable (9 Nov 2026)
**Decision:** `readings` is a hypertable with 1-day chunks and the key `(equipment_id, time)`.
**Why:** a hypertable splits data into time chunks, so recent-data queries stay fast as the table grows. The key allows one reading per fan per moment and supports queries per fan over time.
**Alternatives:** a plain Postgres table. Works at first, but gets slower and is harder to compress or expire later.

## Ingest time as the timestamp (9 Nov 2026)
**Decision:** `time` is set by the ingest service when the message arrives, in UTC.
**Why:** the ESP32 has no real clock, only `uptime_ms` since boot. UTC never jumps, unlike UK local time, which changes twice a year.
**Alternatives:** add a real-time clock or NTP time sync to the ESP32. More accurate, but extra work for under a second of difference. `uptime_ms` is still stored, so I can check timing later.

## Raw payload kept as JSONB (9 Nov 2026)
**Decision:** every row stores the full MQTT message in a `payload` JSONB column, as well as the typed columns.
**Why:** the payload is the ground truth. It keeps fields that have no column yet, and it lets me check that each column holds the right value.
**Alternatives:** columns only. Smaller, but a firmware change or an ingest bug would lose data with no way to recover it.

## Payload-to-column mapping dict (9 Nov 2026)
**Decision:** the ingest service uses a dict that maps each payload key to a readings column. The INSERT is built from it.
**Why:** the firmware and the database can rename fields independently. Adding a column is a one-line change, and the column names and values always stay in the same order.
**Alternatives:** a plain list (works today, because all names match) or a hand-written INSERT (easy to get the order or count wrong).

## AHT20 in the airflow, read every second (9 Nov 2026)
**Decision:** the AHT20 sits in the airflow as an airflow proxy (`airflow_c`). It stays at one reading per second. The read will change from blocking to non-blocking.
**Status:** planned, not built. The current firmware still uses a blocking read. The change is scheduled after phase 1, before the resonance sweep.
**Why:** small airflow changes are useful in the charts and as model input. The current read method also costs sampling time, which a non-blocking read fixes.

**Blocking vs non-blocking:** the ESP32 does one task at a time, in a fast loop. Each second it must take 400 vibration samples (one every 2.5 ms), 100 current samples (one every 10 ms), one AHT20 reading, and send the message.
- **Blocking read (current code):** the ESP32 tells the AHT20 to measure, then waits about 80 ms for the result and does nothing else. Every vibration and current sample due in that time is skipped.
- **Non-blocking read (planned):** the ESP32 tells the AHT20 to measure, then goes straight back to sampling. About 80 ms later, when the result is ready, it collects it. No samples are skipped for the AHT20.

**The numbers:** today, about 19% of each second is lost (vibration samples about 323 of 400, power samples about 81 of 100). That is about 190 ms. The AHT20 wait explains about 80 ms of it. I will measure the rest in the firmware session (possible causes: the sensor library waiting longer than 80 ms, sending the MQTT message, reading the other sensors).

**Alternatives:** read the AHT20 every 5 seconds. Simpler, and the gap happens only once in 5 seconds, but it loses the 1-second airflow detail.

## Data collection order (9 Nov 2026)
**Decision:** finish phase 1 → AHT20 fix → tape the rig in place → resonance sweep → healthy baseline → staged faults.
**Why:** each step depends on the one before. The healthy baseline must exist before any fault, so every fault can be compared with normal. Faults are staged safely, for example Blu-Tack added with the fan stopped.
**Alternatives:** start recording faults straight away. Faster, but with no baseline and with flawed sample counts.

## Bad data handling (11 Nov 2026)
**Decision:** `payload` is `NOT NULL`. Messages that cannot be stored (bad JSON, wrong types) go to a `rejected_messages` table with the time, topic, raw text and error.
**Why:** a NULL payload can only come from a bug in my code, so it should fail loudly. Transmission faults are a real signal, so I keep them as data I can count and chart, not just log lines.
**Alternatives:** allow NULL payloads (hides bugs) or only log bad messages (the signal is lost when the logs rotate).

## Labelling in two layers, all in the UI (11 Nov 2026)
**Decision:** all labels are made in the UI. I record the rig condition (for example "1 g Blu-Tack on blade 3") separately from the data labels, which I select from charts or clusters.
**Why:** the project should prove its own labelling workflow. The rig condition gives independent ground truth for testing, so the evaluation is not circular.
**Alternatives:** labels from an experiment log by start and end time. Simple, but it skips the UI workflow and ignores what the data shows.

## Operating state and condition are separate axes (11 Nov 2026)
**Decision:** every moment has an operating state and a condition. Operating states: unpowered, stopped, starting, spinning up, running, speed change, coasting down. Conditions: normal, imbalance, blocked intake, blocked exhaust, loose mount, speed drift, power loss, and more as I find them.
**Why:** a fault does not disappear during a transient. Imbalance force grows with speed squared, so a spin-up shows it across every speed (run-up / coast-down analysis). Models compare like with like: imbalance during spin-up against normal spin-up, never against steady running. The operating state is mostly worked out from duty, RPM, current and voltage; I only confirm it. I label the condition.
**Alternatives:** one label per moment, with transients kept apart from faults. Simpler, but it throws away the spin-up and coast-down signal and mixes "what the fan is doing" with "what is wrong".
**Note:** labels record what is true. "Potential" or "suspected" is a model's confidence, and belongs in the model outputs, not in labels.

## Connectivity status: online, stale, offline (11 Nov 2026)
**Decision:** each device has a connectivity status. Online: messages arrive. Stale: no message for a few seconds (a timeout in the service). Offline: the MQTT last will says `offline`.
**Why:** connectivity is about the data, not the machine. Stale is needed because the last will can take about 20 seconds (keepalive timeout), and it is never sent if the broker itself stops.
**Alternatives:** rely on the last will only. It misses broker failures and leaves a gap of about 20 seconds where a lost fan still looks healthy.
**Note:** an unpowered fan with a powered ESP32 is still online. It shows as the operating state "unpowered" (about 0 V and 0 mA), not as offline.

## Failed sensor reads are sent as null (11 Nov 2026)
**Decision:** when any sensor read fails, the firmware sends `null` for that field, never `nan`. The ingest service stores it as a NULL in that column and stores the other fields normally.
**Status:** planned, not built. Part of the firmware session.
**Why:** `nan` is not valid JSON, so one failed sensor makes the whole message unreadable, and the good values are lost with it. `null` is valid JSON and means "no value", so only the failed field is missing.
**Alternatives:** keep `nan` and let the dead-letter table catch it (loses all the good fields), or parse `nan` in Python (Postgres JSONB rejects it anyway).

## A fan unit is the fan plus its instruments (11 Nov 2026)
**Decision:** I monitor each fan as one **unit**: the fan itself, plus the instruments that measure it (the ESP32 and its sensors). Any problem in the unit is a fault of that unit, including a failed sensor.

**In the data:** the fan and its instruments are stored as separate equipment under the same system. This tells me *which part* failed: the fan (a **machine fault**, such as imbalance) or a sensor (an **instrument fault**, such as no airflow reading). This matches how Haystack and Brick model a device and the points it measures.

**In the UI:**
- **Fleet view:** each fan unit has one patch. A machine fault or an instrument fault turns that patch to Fault (coral). Worst child wins.
- **Fan view** (click a fan): one geodesic for the whole unit. There is no geodesic per sensor.
- Each fault type has its own **shape** and **callout**, so I can tell them apart at a glance:

| Fault | Colour | Shape | Callout |
|---|---|---|---|
| Imbalance (machine) | coral | spike | `FAN01 · IMBALANCE` |
| Sensor failed (instrument) | coral | affected patch goes dark or hollow, like a missing piece | `FAN01 · SENSOR: AHT20` |

**Why:**
- A NULL from a sensor that should always report means I have lost part of my monitoring. That is a failure and needs action, so it shows at Fault level.
- The action is different, though. For a machine fault, I stop or repair the fan. For an instrument fault, I fix the sensor or wiring. The separate shape and callout stop a loose wire from looking like imbalance.

**Effect on the models:** when a sensor fails, the checks that need it cannot be judged. For example, with no airflow reading, "blocked intake" is unknown. Checks that do not need that sensor carry on.

**Alternatives:**
- One item in the data as well as the UI. Simpler, but I would lose which part failed.
- A geodesic per sensor. Too much detail for the fan view.
- Instrument faults as Watch (amber). Rejected: losing a sensor means losing monitoring.

## Data quality is its own status (11 Nov 2026)
**Decision:** each device has a data quality status (ok, or instrument fault naming the sensor), separate from connectivity, operating state and condition.
**Why:** data can arrive (online) and still be untrustworthy. Connectivity asks "is data arriving?"; data quality asks "can I trust it?".
**Alternatives:** fold it into connectivity. Simpler, but "online with a dead sensor" would have no honest way to show.