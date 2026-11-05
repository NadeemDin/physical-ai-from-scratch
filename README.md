# physical-ai-from-scratch

**Build a live physical AI system end to end: a sensor rig, streaming, physics-informed anomaly detection and a transformer world model.**

<! -- put Rig photos here -->

---

## What is Physical AI?

Most AI were exposed to today works on text and images. **Physical AI** is AI that understands the physical world through sensor data such as vibration, temperature, current and speed, and then acts on what it finds.

Personally I think its one of the most interesting areas of AI. Startups are building foundational models for sensor data, industrial AI companies are applying physics-informed "world-models" to plants and refineries and pre-trained time-series models like Amazon's Chronos are making forecasting available off the shelf

But the hard part isn't the model. its the **data**. Real sensor data is messy, faults are rare and labelled examples of failure hardly exist.

## What I'm building

A physical fan rig with five sensor signals (vibration, current and voltage, RPM, hub temperature and airflow temperature) and a system on top of it that:

- **Streams** readings live from the rig (ESP32 -> MQTT -> Kafka -> TimescaleDB)
- **Forecasts** the fan's next few seconds of readings from its recent behaviour and commanded speed. When reality departs from the forecast, thats an anomaly
- **Detects** anomalies using statistics, physics, clustering, Amazon Chronos and a transformer built from scratch, **compared side by side, live**
- **Checks against physics**: The fan affinity laws predict how speed, current and airflow should relate. Departures from them are flagged
- Lets me **label** new behaviour live, with physics-backed suggestions
- **Explains* what happened in plain English
- **Recursive learning**: Forecasts, checks against what actually happened and retrains on the new data (S3 -> Databricks) with no labels needed

## Why

Most ML projects start from a downloaded dataset. This one stars from wiring sensors to a fan.

Building the rig means I **control the data**: I can physically stage real faults such as but not limited to: blocked airflow, powerloss, blade obstruction. Ill know exactly when they happened and test whether each method actually catches them

My background is in industrial data engineering: onboarding building-automation sensor data from 50+ buildings at a smart-buildings start-up. This project is the next step: going from collecting and organising machine data to building the AI that understands it. 

## Roadmap

### Core: physical AI on a single machine
| Phase | What | Status |
| --- | ---- | ---|
| 0| Rig build and hardware docs | ⬜️ |
| 1 | Docker, MQTT, TimescaleDB, live clusters, labelling UI | ⬜️|
| 2| Kafka: every model reads the same live stream | ⬜️ |
| 3 | AWS (S3, IAM, KMS) and Databricks: the training pipeline | ⬜️ | 
| 4| Physics model, transformer, Chronos, baselines, live comparison, explanations | ⬜️|
| - | White paper and dataset release | ⬜️ |

### Supplementary: scaling to a fleet
| Phase | What | Status |
| ---| --- | --- |
| S1 | Live fleet simulator and fleet dashboard | ⬜️ |
| S2 | Kubernetes: scaling, self-healing, rolling model updates | ⬜️ |
| S3 | AWS EKS and Cloudwatch | ⬜️ | 

## Tools and why

<!-- Filled in as each phase is built: one line per tool on why it's here -->

## Documentation

- [Hardware build](docs/00-hardware.md)
- [Build log: issues and fixes](docs/build-log.md)
- [Design decisions](docs/decisions.md)
- [Experiments and results](docs/experiments.md)

---
**Licence:** MIT