# 🧹 HA Optimizer

**Smart cleanup, analysis and health-check for Home Assistant.**

Automatically finds dead entities, broken automations, database bloat, state storms and silently-failing integrations — and lets you clean them up safely with one-click soft delete and full restore.

## What it detects

- 💀 Stale and orphaned entities (no state change in N days, config entry removed)
- 🤖 Broken automations with dead triggers, actions or conditions
- 🗄️ Top DB writers and wasteful recorder records — with ready-to-paste YAML fixes
- 🌩️ State storms (entities updating 100×/min causing DB bloat)
- 🔌 Integrations with poor reconnect health, weak batteries
- ❓ Anomalies in your HA's own behaviour vs its 30-day personal baseline

## Safety first

Smoke detectors, CO/gas sensors, door/window, locks and motion sensors are **never** suggested for deletion. Soft delete is the default — everything is reversible.

## No dependencies

Uses only Home Assistant built-ins. Works with SQLite and MySQL/MariaDB.
