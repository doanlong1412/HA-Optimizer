# Changelog

All notable changes to **HA Optimizer** will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2025-04-19

### Added
- 🔍 **Smart Entity Scanner** — full scan of entities, automations, scripts and helpers with risk-level scoring (Low / Medium / High) and a `health_score` (0–100) for the HA instance
- 🗑️ **Safe Purge Engine** — soft delete (disable, reversible) and hard delete with trash tracking, timestamped entries and configurable auto-expiry
- ♻️ **Restore Service** — re-enable any soft-deleted entity with one service call
- 📡 **Fingerprint Anomaly Detection** — compares today's HA behaviour against a personal 30-day rolling baseline using σ / IQR statistics; detects spikes in state writes, automation triggers, unavailability events and HA lifecycle events
- 🗄️ **Recorder DB Analyzer** — queries SQLite and MySQL/MariaDB directly; identifies top-writing entities, wasteful records and generates ready-to-paste YAML optimizations
- 📊 **Lovelace Dashboard Auditor** — reads `.storage/lovelace*`; flags heavy cards, missing entities, duplicate references, uninstalled custom cards and Jinja2 template cards
- 🌩️ **State Storm Detector** — finds entities updating state abnormally fast vs their domain baseline, with severity rating and fix suggestions
- 🤖 **Automation Dead Code Analyzer** — scans UI-created automations for broken triggers, actions and conditions referencing removed entities/devices/services
- 🔌 **Integration Health Scorer** — 7-day reconnect and unavailability analysis per integration with battery-level diagnosis
- ⚙️ **Full UI Config Flow** — setup and options entirely through the HA UI, no YAML required
- 🛡️ **Safety hardcodes** — smoke, CO/gas, moisture, motion, door, window, lock and battery device classes are never suggested for deletion
- 🔄 **Auto-scan** — configurable interval (days); set to 0 to disable
- ⏰ **Daily baseline collection** — automatic fingerprint snapshot at 00:05 each day
- 🔗 **Sidebar panel** — dedicated HA Optimizer panel registered in the HA sidebar

---

*Previous versions not tracked (initial release).*
