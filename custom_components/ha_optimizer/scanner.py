"""Data Scanner - Registry and Reference Scanner for HA Optimizer."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import (
    CAT_AUTOMATION, CAT_ENTITY, CAT_HELPER, CAT_SCRIPT,
    RISK_HIGH, RISK_LOW, RISK_MEDIUM,
    SAFETY_DEVICE_CLASSES, SUSPICIOUS_PATTERNS,
)

_LOGGER = logging.getLogger(__name__)

# Helper entity domains
HELPER_DOMAINS = {
    "input_boolean", "input_number", "input_select", "input_text",
    "input_datetime", "counter", "timer", "schedule",
    "input_button", "todo",
}


class ScanResult:
    """Represents a single scan result item."""

    def __init__(
        self,
        entity_id: str,
        name: str,
        category: str,
        risk_level: str,
        reason: list[str],
        domain: str = "",
        device_class: str | None = None,
        last_changed: datetime | None = None,
        used_in: list[str] | None = None,
        platform: str | None = None,
        config_entry_id: str | None = None,
        yaml_location: dict | None = None,
        is_yaml_entity: bool = False,
        disabled: bool = False,
        unique_id: str | None = None,
    ):
        self.entity_id = entity_id
        self.name = name
        self.category = category
        self.risk_level = risk_level
        self.reason = reason
        self.domain = domain
        self.device_class = device_class
        self.last_changed = last_changed
        self.used_in = used_in or []
        self.platform = platform
        self.config_entry_id = config_entry_id
        self.yaml_location = yaml_location  # {"file": "...", "line": N}
        self.is_yaml_entity = is_yaml_entity
        self.disabled = disabled
        self.unique_id = unique_id  # HA storage ID — used for editor deep links

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "category": self.category,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "domain": self.domain,
            "device_class": self.device_class,
            "last_changed": self.last_changed.isoformat() if self.last_changed else None,
            "used_in": self.used_in,
            "platform": self.platform,
            "config_entry_id": self.config_entry_id,
            "yaml_location": self.yaml_location,
            "is_yaml_entity": self.is_yaml_entity,
            "disabled": self.disabled,
            "unique_id": self.unique_id,
        }


class DataScanner:
    """Main scanner class that orchestrates registry and reference scanning."""

    def __init__(self, hass: HomeAssistant, options: dict):
        self.hass = hass
        self.options = options
        self.stale_days = options.get("stale_days_threshold", 30)
        self.exclude_classes_raw = options.get("exclude_device_classes", "")
        self.excluded_classes = {
            c.strip().lower()
            for c in self.exclude_classes_raw.split(",")
            if c.strip()
        } | SAFETY_DEVICE_CLASSES

    async def async_scan(self) -> dict[str, Any]:
        """Run full scan and return structured results."""
        _LOGGER.info("HA Optimizer: Starting scan...")

        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)

        # Gather references from YAML and dashboards
        references = await self.hass.async_add_executor_job(self._scan_references)

        # Gather state history via SQL — returns {entity_id: {last_any, last_valid}}
        history_map = await self._get_history_map()

        # Build active config entry IDs for O(1) dead-entry detection (Method 2)
        active_entry_ids: set[str] = {
            e.entry_id for e in self.hass.config_entries.async_entries()
        }

        results: list[ScanResult] = []

        for entry in ent_reg.entities.values():
            try:
                result = self._analyze_entity(
                    entry, dev_reg, references, history_map, active_entry_ids
                )
                if result:
                    results.append(result)
            except Exception as exc:
                _LOGGER.warning("Error analyzing entity %s: %s", entry.entity_id, exc)

        # Scan automations
        automation_results = await self._scan_automations(references)
        results.extend(automation_results)

        # Scan scripts
        script_results = await self._scan_scripts(references)
        results.extend(script_results)

        # Build statistics
        total = len(ent_reg.entities)
        found = len(results)
        by_risk = {RISK_LOW: 0, RISK_MEDIUM: 0, RISK_HIGH: 0}
        by_cat = {CAT_ENTITY: 0, CAT_AUTOMATION: 0, CAT_SCRIPT: 0, CAT_HELPER: 0}
        for r in results:
            by_risk[r.risk_level] = by_risk.get(r.risk_level, 0) + 1
            by_cat[r.category] = by_cat.get(r.category, 0) + 1

        health_score = max(0, 100 - int((found / max(total, 1)) * 100))

        _LOGGER.info("HA Optimizer: Scan complete. Found %d candidates from %d total.", found, total)

        return {
            "results": [r.to_dict() for r in results],
            "statistics": {
                "total_entities": total,
                "candidates_found": found,
                "health_score": health_score,
                "by_risk": by_risk,
                "by_category": by_cat,
                "scanned_at": dt_util.utcnow().isoformat(),
            },
        }

    # Platforms that are naturally often unavailable — not orphans
    _SKIP_UNAVAILABLE_PLATFORMS = {
        "template", "group", "universal", "input_boolean",
        "input_number", "input_select", "input_text", "input_datetime",
        "counter", "timer", "schedule",
    }

    def _analyze_entity(
        self,
        entry: er.RegistryEntry,
        dev_reg: dr.DeviceRegistry,
        references: dict,
        history_map: dict,
        active_entry_ids: set,
    ) -> ScanResult | None:
        """Analyze a single entity — 4-method detection from Orphan Entity Cleaner.

        Method 1 — orphaned_timestamp : official HA field set after restart
        Method 2 — dead_config_entry  : config_entry_id points to removed integration
        Method 3 — unavailable_state  : state=unavailable for >= stale_days
                                        uses entry.modified_at (survives restarts),
                                        NOT state.last_changed (resets on restart)
        Method 4 — stale_recorder     : last VALID (non-unavailable) state in recorder
                                        is older than stale_days threshold
        """
        entity_id = entry.entity_id
        domain    = entity_id.split(".")[0]
        platform  = entry.platform or ""
        reasons   = []
        risk      = RISK_MEDIUM
        last_changed_dt = None  # best datetime to show in UI

        # ── Skip system/internal domains ─────────────────────────────
        if domain in ("persistent_notification",) and not platform:
            return None

        # ── Skip safety device classes (smoke, motion, lock, etc.) ───
        device_class = entry.original_device_class or entry.device_class
        if device_class and device_class.lower() in self.excluded_classes:
            return None

        # ── Determine category ────────────────────────────────────────
        category = CAT_HELPER if domain in HELPER_DOMAINS else CAT_ENTITY

        # ── Method 1: orphaned_timestamp (official HA field) ─────────
        orphaned_ts = getattr(entry, "orphaned_timestamp", None)
        if orphaned_ts is not None:
            import time as _time
            age_h = (_time.time() - orphaned_ts) / 3600
            age_d = int(age_h / 24)
            if age_h >= 24:
                reasons.append(f"Orphaned by HA for {age_d} days (official)")
                risk = RISK_LOW
                last_changed_dt = datetime.utcfromtimestamp(orphaned_ts).replace(
                    tzinfo=dt_util.UTC
                )

        # ── Method 2: dead config entry ──────────────────────────────
        is_dead_entry = False
        if not reasons and entry.config_entry_id:
            if entry.config_entry_id not in active_entry_ids:
                is_dead_entry = True
                reasons.append("Integration removed (config entry gone)")
                risk = RISK_LOW

        # ── Method 3: unavailable state (Orphan Cleaner key insight) ─
        # Uses entry.modified_at from the registry — this survives HA
        # restarts unlike state.last_changed which resets every boot.
        # Only applies to entities that are NOT disabled and NOT on
        # platforms that are naturally unavailable.
        is_unavailable = False
        if (
            not reasons
            and entry.disabled_by is None
            and platform not in self._SKIP_UNAVAILABLE_PLATFORMS
        ):
            cur_state = self.hass.states.get(entity_id)
            if cur_state and cur_state.state == "unavailable":
                # Prefer registry modified_at (survives restart) over
                # state.last_changed (resets on boot)
                modified_at = getattr(entry, "modified_at", None)
                created_at  = getattr(entry, "created_at", None)
                ref_dt = modified_at or created_at
                if ref_dt:
                    age_h = (dt_util.utcnow() - ref_dt).total_seconds() / 3600
                    age_d = int(age_h / 24)
                    if age_d >= 1:  # at least 1 full day
                        is_unavailable = True
                        reasons.append(f"Unavailable for {age_d} day{'s' if age_d != 1 else ''}")
                        risk = RISK_MEDIUM
                        last_changed_dt = ref_dt

        # ── Method 4: stale recorder (last VALID state is old) ───────
        # Key fix vs old code: we use last_valid (non-unavailable writes)
        # not last_any — so an entity spamming "unavailable" every 30s
        # is correctly flagged instead of looking "fresh".
        stale = False
        if not reasons or (is_unavailable and not last_changed_dt):
            rec = history_map.get(entity_id)  # dict with last_any / last_valid
            if rec:
                last_valid = rec.get("last_valid")
                last_any   = rec.get("last_any")
                # Use last_valid for stale check; fall back to last_any for display
                check_dt = last_valid or last_any
                if last_valid:
                    age_days = (dt_util.utcnow() - last_valid).days
                    if age_days >= self.stale_days:
                        stale = True
                        reasons.append(f"No real state change in {age_days} days")
                        risk = RISK_LOW
                last_changed_dt = last_changed_dt or last_valid or last_any

        # ── Tier-2/3 fallback for display datetime ────────────────────
        if last_changed_dt is None:
            _s = self.hass.states.get(entity_id)
            if _s and _s.last_changed:
                last_changed_dt = _s.last_changed
        if last_changed_dt is None:
            created_at = getattr(entry, "created_at", None)
            if created_at:
                last_changed_dt = created_at

        # ── No reason found → entity is healthy, skip ─────────────────
        if not reasons:
            return None

        # ── Suspicious naming check ───────────────────────────────────
        name_lower = (entry.name or entry.original_name or entity_id).lower()
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern in name_lower:
                reasons.append(f"Suspicious name: '{pattern}'")
                break

        # ── References: YAML + runtime ────────────────────────────────
        used_in = self._enrich_runtime_usage(entity_id, list(references.get(entity_id, [])))

        # ── Final risk level ──────────────────────────────────────────
        if orphaned_ts or is_dead_entry:
            risk = RISK_LOW
        elif is_unavailable and used_in:
            risk = RISK_HIGH    # broken but still referenced
        elif is_unavailable and not used_in:
            risk = RISK_MEDIUM
        elif stale and not used_in:
            risk = RISK_LOW
        elif stale and used_in:
            risk = RISK_MEDIUM

        # ── YAML detection ────────────────────────────────────────────
        is_yaml = entry.platform in ("template", "group", "command_line") or entry.config_entry_id is None
        display_name = entry.name or entry.original_name or entity_id

        return ScanResult(
            entity_id=entity_id,
            name=display_name,
            category=category,
            risk_level=risk,
            reason=reasons,
            domain=domain,
            device_class=device_class,
            last_changed=last_changed_dt,
            used_in=used_in,
            platform=platform,
            config_entry_id=entry.config_entry_id,
            is_yaml_entity=is_yaml,
            disabled=entry.disabled,
            unique_id=entry.unique_id,
        )

    async def _scan_automations(self, references: dict) -> list[ScanResult]:
        """Scan automations for unused ones."""
        results = []
        try:
            automations = self.hass.states.async_all("automation")
            history_map = await self._get_history_map_for_domain("automation")
            ent_reg = er.async_get(self.hass)

            for state in automations:
                entity_id = state.entity_id
                reasons = []
                risk = RISK_MEDIUM
                name = state.attributes.get("friendly_name", entity_id)
                name_lower = name.lower()

                last_triggered = state.attributes.get("last_triggered")
                last_dt = None
                if last_triggered:
                    try:
                        last_dt = datetime.fromisoformat(str(last_triggered).replace("Z", "+00:00"))
                        age_days = (dt_util.utcnow() - last_dt).days
                        if age_days >= 90:
                            reasons.append(f"Not triggered in {age_days} days (>90)")
                            risk = RISK_LOW
                    except (ValueError, TypeError):
                        pass
                else:
                    reasons.append("Never been triggered")
                    risk = RISK_LOW

                # Suspicious names
                for pattern in SUSPICIOUS_PATTERNS:
                    if pattern in name_lower:
                        reasons.append(f"Suspicious name: '{pattern}'")
                        break

                if state.state == "off":
                    reasons.append("Automation is currently disabled")

                if not reasons:
                    continue

                # Get unique_id (numeric storage ID) from entity registry
                # This is what HA uses in the editor URL: /config/automation/edit/{unique_id}
                reg_entry = ent_reg.async_get(entity_id)
                unique_id = reg_entry.unique_id if reg_entry else None

                used_in = self._enrich_runtime_usage(entity_id, list(references.get(entity_id, [])))
                results.append(ScanResult(
                    entity_id=entity_id,
                    name=name,
                    category=CAT_AUTOMATION,
                    risk_level=risk,
                    reason=reasons,
                    domain="automation",
                    last_changed=last_dt,
                    used_in=used_in,
                    unique_id=unique_id,
                ))
        except Exception as exc:
            _LOGGER.warning("Error scanning automations: %s", exc)
        return results

    async def _scan_scripts(self, references: dict) -> list[ScanResult]:
        """Scan scripts for unused ones."""
        results = []
        try:
            scripts = self.hass.states.async_all("script")
            ent_reg = er.async_get(self.hass)
            for state in scripts:
                entity_id = state.entity_id
                reasons = []
                name = state.attributes.get("friendly_name", entity_id)
                name_lower = name.lower()

                # last_triggered lives in state.attributes for scripts (not recorder)
                last_triggered_raw = state.attributes.get("last_triggered")
                last_dt = None
                if last_triggered_raw:
                    try:
                        last_dt = datetime.fromisoformat(
                            str(last_triggered_raw).replace("Z", "+00:00")
                        )
                        age_days = (dt_util.utcnow() - last_dt).days
                        if age_days >= 90:
                            reasons.append(f"Script not run in {age_days} days (>90)")
                    except (ValueError, TypeError):
                        pass
                else:
                    reasons.append("Script has never been run")

                for pattern in SUSPICIOUS_PATTERNS:
                    if pattern in name_lower:
                        reasons.append(f"Suspicious name pattern: '{pattern}'")
                        break

                if not reasons:
                    continue

                # Combine YAML refs + runtime usage from automation/script/group states
                used_in = self._enrich_runtime_usage(entity_id, list(references.get(entity_id, [])))

                # Get unique_id from entity registry
                reg_entry = ent_reg.async_get(entity_id)
                unique_id = reg_entry.unique_id if reg_entry else None

                results.append(ScanResult(
                    entity_id=entity_id,
                    name=name,
                    category=CAT_SCRIPT,
                    risk_level=RISK_LOW if not used_in else RISK_MEDIUM,
                    reason=reasons,
                    domain="script",
                    last_changed=last_dt,
                    used_in=used_in,
                    unique_id=unique_id,
                ))
        except Exception as exc:
            _LOGGER.warning("Error scanning scripts: %s", exc)
        return results

    def _enrich_runtime_usage(self, entity_id: str, existing: list) -> list:
        """Check runtime states for references to entity_id."""
        used = list(existing)
        seen = set(existing)

        for state in self.hass.states.async_all("automation"):
            if entity_id in str(state.attributes):
                loc = f"automation:{state.entity_id}"
                if loc not in seen:
                    used.append(loc)
                    seen.add(loc)

        for state in self.hass.states.async_all("script"):
            if state.entity_id == entity_id:
                continue
            if entity_id in str(state.attributes):
                loc = f"script:{state.entity_id}"
                if loc not in seen:
                    used.append(loc)
                    seen.add(loc)

        for state in self.hass.states.async_all("group"):
            members = state.attributes.get("entity_id", [])
            if entity_id in members:
                loc = f"group:{state.entity_id}"
                if loc not in seen:
                    used.append(loc)
                    seen.add(loc)

        return used

    def _scan_references(self) -> dict[str, list[str]]:
        """Scan YAML files and return a map of entity_id -> [usage locations]."""
        references: dict[str, list[str]] = {}
        config_dir = self.hass.config.config_dir

        def add_ref(entity_id: str, location: str):
            if entity_id not in references:
                references[entity_id] = []
            if location not in references[entity_id]:
                references[entity_id].append(location)

        yaml_extensions = (".yaml", ".yml")

        for root, dirs, files in os.walk(config_dir):
            # Skip hidden dirs and node_modules
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]

            for filename in files:
                if not any(filename.endswith(ext) for ext in yaml_extensions):
                    continue

                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, config_dir)

                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # Find all entity_id-like patterns
                    pattern = re.compile(
                        r'\b([a-z_]+\.[a-z0-9_]+)\b',
                        re.IGNORECASE
                    )
                    for match in pattern.finditer(content):
                        candidate = match.group(1).lower()
                        domain_part = candidate.split(".")[0]
                        # Filter to known HA domains
                        if domain_part in _KNOWN_DOMAINS:
                            add_ref(candidate, f"yaml:{rel_path}")

                except Exception as exc:
                    _LOGGER.debug("Could not scan %s: %s", filepath, exc)

        return references

    async def _get_history_map(self) -> dict[str, datetime]:
        """Get last_changed for all entities from the recorder DB."""
        return await self.hass.async_add_executor_job(self._query_history_all)

    async def _get_history_map_for_domain(self, domain: str) -> dict[str, datetime]:
        return await self.hass.async_add_executor_job(self._query_history_domain, domain)

    def _query_history_all(self) -> dict[str, dict]:
        """Query recorder DB for per-entity state history.

        Inspired by Orphan Entity Cleaner: distinguish between
        - last_any   : last time ANY state was written (incl. unavailable)
        - last_valid : last time a real (non-unavailable/unknown) state was written

        An entity whose last_valid is old but last_any is recent is one that
        keeps reporting unavailable — it must still be flagged, not skipped.
        """
        result = {}
        try:
            from homeassistant.components.recorder import get_instance
            from sqlalchemy import text

            instance = get_instance(self.hass)
            with instance.get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT entity_id, "
                        "  MAX(last_updated_ts) AS last_any_ts, "
                        "  MAX(CASE WHEN state NOT IN "
                        "    ('unavailable','unknown','none','') "
                        "    THEN last_updated_ts END) AS last_valid_ts "
                        "FROM states "
                        "GROUP BY entity_id"
                    )
                ).fetchall()
                for row in rows:
                    try:
                        entity_id   = row[0]
                        last_any_ts   = row[1]
                        last_valid_ts = row[2]
                        if last_any_ts:
                            result[entity_id] = {
                                "last_any": datetime.utcfromtimestamp(
                                    float(last_any_ts)
                                ).replace(tzinfo=dt_util.UTC),
                                "last_valid": (
                                    datetime.utcfromtimestamp(
                                        float(last_valid_ts)
                                    ).replace(tzinfo=dt_util.UTC)
                                    if last_valid_ts else None
                                ),
                            }
                    except (ValueError, TypeError):
                        pass
        except Exception as exc:
            _LOGGER.warning("Could not query recorder history: %s", exc)
        return result

    def _query_history_domain(self, domain: str) -> dict[str, datetime]:
        result = {}
        try:
            from homeassistant.components.recorder import get_instance
            from sqlalchemy import text

            instance = get_instance(self.hass)
            with instance.get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT entity_id, MAX(last_updated_ts) as last_ts "
                        "FROM states "
                        f"WHERE entity_id LIKE '{domain}.%' "
                        "GROUP BY entity_id"
                    )
                ).fetchall()
                for row in rows:
                    try:
                        if row[1]:
                            result[row[0]] = datetime.utcfromtimestamp(float(row[1])).replace(
                                tzinfo=dt_util.UTC
                            )
                    except (ValueError, TypeError):
                        pass
        except Exception as exc:
            _LOGGER.debug("Could not query history for domain %s: %s", domain, exc)
        return result


# Known HA domains for reference scanning
_KNOWN_DOMAINS = {
    "sensor", "binary_sensor", "switch", "light", "cover", "fan",
    "climate", "media_player", "camera", "alarm_control_panel",
    "lock", "vacuum", "water_heater", "automation", "script",
    "scene", "input_boolean", "input_number", "input_select",
    "input_text", "input_datetime", "counter", "timer",
    "device_tracker", "person", "zone", "sun", "weather",
    "group", "template", "schedule", "todo", "button",
    "event", "update", "number", "select", "text",
}


# ================================================================
# RECORDER ANALYZER
# ================================================================

class RecorderAnalyzer:
    """Analyzes recorder DB to find expensive entities and suggest optimizations."""

    def __init__(self, hass):
        self.hass = hass

    async def async_analyze(self) -> dict:
        return await self.hass.async_add_executor_job(self._run_analysis)

    def _run_analysis(self) -> dict:
        result = {
            "top_writers": [],
            "wasteful_entities": [],
            "domain_stats": [],
            "db_size_mb": None,
            "total_states_count": 0,
            "commit_interval_suggestion": 5,
            "yaml_exclude_suggestion": "",
            "db_type": "unknown",
            "error": None,
        }
        try:
            from homeassistant.components.recorder import get_instance
            from sqlalchemy import text

            instance = get_instance(self.hass)
            with instance.get_session() as session:

                # Detect DB type — SQLite vs MySQL/MariaDB
                db_url = str(instance.engine.url)
                is_mysql = "mysql" in db_url or "mariadb" in db_url
                result["db_type"] = "mysql" if is_mysql else "sqlite"

                # Timestamp expression: 30 days ago as unix epoch
                if is_mysql:
                    ts_30d = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 30 DAY))"
                    ts_1d  = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 1 DAY))"
                    # MySQL uses SUBSTRING_INDEX for domain extraction
                    domain_expr = "SUBSTRING_INDEX(entity_id, '.', 1)"
                else:
                    ts_30d = "strftime('%s', 'now', '-30 days')"
                    ts_1d  = "strftime('%s', 'now', '-1 day')"
                    domain_expr = "substr(entity_id, 1, instr(entity_id, '.') - 1)"

                # 1. Total state count
                total = session.execute(text("SELECT COUNT(*) FROM states")).scalar() or 0
                result["total_states_count"] = total

                # 2. Top 20 entities by record count
                rows = session.execute(text("""
                    SELECT entity_id, COUNT(*) as cnt
                    FROM states
                    GROUP BY entity_id
                    ORDER BY cnt DESC
                    LIMIT 20
                """)).fetchall()
                result["top_writers"] = [
                    {"entity_id": r[0], "count": r[1]}
                    for r in rows if r[0]
                ]

                # 3. Wasteful: many records but value rarely changes (last 30 days)
                # NOTE: MySQL forbids aliases of aggregate functions in ORDER BY,
                # so we must repeat the full expression — works on both MySQL and SQLite.
                if is_mysql:
                    waste_order_expr = "CAST(COUNT(*) AS DECIMAL(12,2)) / COUNT(DISTINCT state)"
                else:
                    waste_order_expr = "CAST(COUNT(*) AS FLOAT) / COUNT(DISTINCT state)"

                waste_sql = f"""
                    SELECT
                        entity_id,
                        COUNT(*) as total_records,
                        COUNT(DISTINCT state) as distinct_states
                    FROM states
                    WHERE last_updated_ts > {ts_30d}
                    GROUP BY entity_id
                    HAVING COUNT(*) > 50 AND COUNT(DISTINCT state) <= 3
                    ORDER BY {waste_order_expr} DESC
                    LIMIT 20
                """
                waste_rows = session.execute(text(waste_sql)).fetchall()
                result["wasteful_entities"] = [
                    {
                        "entity_id": r[0],
                        "total_records": r[1],
                        "distinct_states": r[2],
                        "waste_ratio": round(r[1] / max(r[2], 1), 1),
                    }
                    for r in waste_rows if r[0]
                ]

                # 4. Domain summary
                domain_sql = f"""
                    SELECT
                        {domain_expr} as domain,
                        COUNT(*) as cnt
                    FROM states
                    GROUP BY domain
                    ORDER BY cnt DESC
                    LIMIT 15
                """
                domain_rows = session.execute(text(domain_sql)).fetchall()
                result["domain_stats"] = [
                    {"domain": r[0], "count": r[1]}
                    for r in domain_rows if r[0]
                ]

                # 5. DB size
                try:
                    if is_mysql:
                        # MySQL: query information_schema for DB size
                        size_row = session.execute(text("""
                            SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 1)
                            FROM information_schema.tables
                            WHERE table_schema = DATABASE()
                        """)).scalar()
                        if size_row:
                            result["db_size_mb"] = float(size_row)
                    else:
                        db_path_row = session.execute(text("PRAGMA database_list")).fetchone()
                        if db_path_row and db_path_row[2]:
                            import os
                            size = os.path.getsize(db_path_row[2])
                            result["db_size_mb"] = round(size / 1024 / 1024, 1)
                except Exception:
                    pass

                # 6. commit_interval suggestion based on states/min in last day
                rate_sql = f"""
                    SELECT COUNT(*) / 1440.0
                    FROM states
                    WHERE last_updated_ts > {ts_1d}
                """
                rate_row = session.execute(text(rate_sql)).scalar() or 0
                if rate_row < 10:
                    result["commit_interval_suggestion"] = 10
                elif rate_row < 50:
                    result["commit_interval_suggestion"] = 5
                else:
                    result["commit_interval_suggestion"] = 3

                # 7. Generate YAML suggestion
                exclude_ids = list({r["entity_id"] for r in result["wasteful_entities"][:10]})
                exclude_domains = [
                    d["domain"] for d in result["domain_stats"]
                    if d["domain"] in ("sun", "weather", "zone", "update") and d["count"] > 100
                ]
                yaml_lines = [
                    "recorder:",
                    f"  commit_interval: {result['commit_interval_suggestion']}",
                    "  exclude:",
                ]
                if exclude_domains:
                    yaml_lines.append("    domains:")
                    for dom in exclude_domains:
                        yaml_lines.append(f"      - {dom}")
                if exclude_ids:
                    yaml_lines.append("    entities:")
                    for eid in exclude_ids:
                        yaml_lines.append(f"      - {eid}")
                result["yaml_exclude_suggestion"] = "\n".join(yaml_lines)

        except Exception as exc:
            result["error"] = str(exc)
            _LOGGER.warning("RecorderAnalyzer error: %s", exc)

        return result


# ================================================================
# DASHBOARD ANALYZER
# ================================================================

class DashboardAnalyzer:
    """
    Phân tích toàn diện Lovelace dashboards từ .storage/lovelace*.

    Phát hiện:
      1.  Heavy cards (expanded list + severity scoring)
      2.  Views quá nhiều card (>30 gây lag khi load)
      3.  Entity missing — không tồn tại trong HA registry
      4.  Entity unavailable/unknown — tồn tại nhưng đang lỗi
      5.  Duplicate entity — cùng entity xuất hiện >5 lần
      6.  history-graph / statistics-graph với nhiều entity (>5)
      7.  Custom card chưa cài — type bắt đầu custom: nhưng không
          có trong frontend resource list
      8.  Template nặng — card có Jinja2 template trong fields quan trọng
      9.  WebSocket push pressure — entity trong dashboard update bao
          nhiêu lần/ngày → đo gánh nặng thực tế lên browser
      10. View complexity score — nesting depth, số entity, số template,
          số DB query mỗi view; không phụ thuộc tên card
      11. Recorder cross-reference — entity trong dashboard update nhiều
          nhưng ít distinct states → lãng phí DB + bandwidth
    """

    # --- Heavy card definitions ---
    HEAVY_CARD_SEVERITY: dict[str, tuple[str, str]] = {
        "camera":                      ("critical", "Live camera stream — high bandwidth & CPU usage"),
        "map":                         ("critical",  "Heavy map render, slow to load on mobile"),
        "iframe":                      ("critical",  "Loads external page in iframe, uncontrolled performance"),
        "custom:apexcharts-card":      ("critical",  "Heavy chart, redraws on every entity update"),
        "custom:power-flow-card":      ("critical",  "Realtime animation, high CPU when visible"),
        "custom:floorplan":            ("critical",  "Complex SVG floorplan, slow to load"),
        "custom:plotly-graph-card":    ("critical",  "Client-side Plotly render, very heavy"),
        "custom:mini-graph-card":      ("warning",   "Graph card, heavier than built-in history-graph"),
        "custom:bubble-card":          ("warning",   "Many animations, heavy on mobile"),
        "custom:mushroom-chips-card":  ("info",      "Many chips continuously polling entities"),
        "custom:stack-in-card":        ("info",      "Container card, weight depends on inner cards"),
        "custom:auto-entities":        ("warning",   "Dynamic entity query, runs filter on every update"),
        "custom:config-template-card": ("warning",   "Continuously evaluates Jinja2 client-side"),
        "custom:decluttering-card":    ("info",      "Template expansion, verify inner cards"),
        "history-graph":               ("warning",   "Queries DB on every load, heavy with many entities"),
        "statistics-graph":            ("warning",   "Queries long-term stats DB, heavy with many entities"),
        "energy":                      ("warning",   "Energy dashboard, many DB queries"),
        "logbook":                     ("warning",   "Continuously queries logbook DB"),
        "todo":                        ("info",      "Polls todo list"),
    }

    # Ngưỡng
    VIEW_CARD_LIMIT         = 30
    VIEW_CARD_CRITICAL      = 60
    DUPLICATE_THRESHOLD     = 5
    GRAPH_ENTITY_WARNING    = 5
    GRAPH_ENTITY_CRITICAL   = 10
    # WebSocket pressure: entity update > N lần/ngày trong dashboard = cảnh báo
    WS_PUSH_WARNING         = 200    # times/day
    WS_PUSH_CRITICAL        = 500
    # Cross-ref: entity trong dash update nhiều nhưng distinct states thấp
    XREF_WRITES_WARNING     = 300    # writes/day
    XREF_WASTE_RATIO        = 10.0   # writes / distinct_states
    # Complexity thresholds per view
    COMPLEXITY_WARN         = 50
    COMPLEXITY_CRITICAL     = 100

    _TEMPLATE_FIELDS = (
        "state_color", "name", "icon", "content", "label",
        "secondary", "badge_color", "badge_icon",
        "tap_action", "hold_action", "double_tap_action",
    )
    # card types that each trigger a recorder/DB query on load
    _DB_QUERY_CARDS = {"history-graph", "statistics-graph", "energy", "logbook"}

    def __init__(self, hass):
        self.hass = hass

    async def async_analyze(self) -> dict:
        return await self.hass.async_add_executor_job(self._run_analysis)

    # ------------------------------------------------------------------
    # Main runner
    # ------------------------------------------------------------------
    def _run_analysis(self) -> dict:
        import json, os, glob

        result = {
            "dashboards": [],
            "heavy_cards": [],
            "overloaded_views": [],
            "missing_entities": [],
            "unavailable_entities": [],
            "duplicate_entities": [],
            "heavy_graphs": [],
            "unconfigured_custom_cards": [],
            "template_heavy_cards": [],
            # NEW
            "view_complexity": [],          # per-view complexity score breakdown
            "ws_pressure": [],              # entity → pushes/day → browser impact
            "recorder_crossref": [],        # entity in dash × recorder write stats
            "total_entity_refs": 0,
            "summary": {},
            "error": None,
        }

        try:
            storage_dir = os.path.join(self.hass.config.config_dir, ".storage")
            lovelace_files = glob.glob(os.path.join(storage_dir, "lovelace*"))

            registered_custom_cards = self._get_registered_custom_cards(storage_dir)

            all_state_ids  = {s.entity_id for s in self.hass.states.async_all()}
            unavail_states = {
                s.entity_id
                for s in self.hass.states.async_all()
                if s.state in ("unavailable", "unknown")
            }

            global_entity_counter: dict[str, int] = {}
            all_entity_refs_set:   set[str]        = set()
            # For complexity: collect per-view entity sets
            per_view_entity_sets: list[tuple[str, str, set[str]]] = []  # (dash, view, entities)

            dashboard_summary = []

            for filepath in lovelace_files:
                try:
                    with open(filepath, encoding="utf-8") as f:
                        raw = json.load(f)
                except Exception as e:
                    _LOGGER.debug("Cannot parse %s: %s", filepath, e)
                    continue

                dash_name = (
                    os.path.basename(filepath)
                    .replace("lovelace.", "")
                    .replace("lovelace", "default")
                )
                config = raw.get("data", {}).get("config", {})
                views  = config.get("views", [])

                dash_card_count  = 0
                dash_heavy_count = 0
                dash_entity_set: set[str] = set()

                for view in views:
                    view_title = view.get("title") or view.get("path") or "unnamed"
                    view_top_cards: list[dict] = []
                    self._collect_top_level_cards(view, view_top_cards)

                    view_all_cards: list[dict] = []
                    for c in view_top_cards:
                        self._flatten_cards(c, view_all_cards)

                    card_count = len(view_all_cards)
                    dash_card_count += card_count

                    # ── View overload ──
                    if card_count > self.VIEW_CARD_LIMIT:
                        sev = "critical" if card_count > self.VIEW_CARD_CRITICAL else "warning"
                        result["overloaded_views"].append({
                            "dashboard": dash_name,
                            "view": view_title,
                            "card_count": card_count,
                            "severity": sev,
                            "suggestion": (
                                f"View '{view_title}' has {card_count} cards — split into multiple views or use tabs/subviews"
                            ),
                        })

                    # ── Per-view complexity measurement (NEW #2) ──
                    view_entity_set:    set[str] = set()
                    view_template_count = 0
                    view_db_queries     = 0
                    view_max_depth      = 0
                    view_custom_count   = 0

                    for top_card in view_top_cards:
                        depth = self._measure_depth(top_card)
                        if depth > view_max_depth:
                            view_max_depth = depth

                    for card in view_all_cards:
                        card_type = card.get("type", "unknown")

                        # 1. Heavy card
                        if card_type in self.HEAVY_CARD_SEVERITY:
                            sev, reason = self.HEAVY_CARD_SEVERITY[card_type]
                            dash_heavy_count += 1
                            entry = {
                                "dashboard": dash_name,
                                "view": view_title,
                                "type": card_type,
                                "title": card.get("title") or card.get("name") or "",
                                "severity": sev,
                                "reason": reason,
                            }
                            if card_type in ("history-graph", "statistics-graph"):
                                egraph = self._extract_graph_entities(card)
                                n = len(egraph)
                                if n > self.GRAPH_ENTITY_WARNING:
                                    result["heavy_graphs"].append({
                                        "dashboard": dash_name,
                                        "view": view_title,
                                        "type": card_type,
                                        "title": entry["title"],
                                        "entity_count": n,
                                        "entities": egraph[:15],
                                        "severity": "critical" if n > self.GRAPH_ENTITY_CRITICAL else "warning",
                                        "reason": (
                                            f"{card_type} with {n} entities — queries {n} separate DB series on every load"
                                        ),
                                    })
                            result["heavy_cards"].append(entry)

                        # 2. Custom card chưa cài
                        if card_type.startswith("custom:"):
                            view_custom_count += 1
                            if card_type not in registered_custom_cards:
                                result["unconfigured_custom_cards"].append({
                                    "dashboard": dash_name,
                                    "view": view_title,
                                    "type": card_type,
                                    "title": card.get("title") or card.get("name") or "",
                                    "severity": "warning",
                                    "reason": (
                                        f"'{card_type}' not in resource list — "
                                        f"card will show 'Custom element doesn't exist'"
                                    ),
                                })

                        # 3. Template detection
                        tmpl_fields = self._detect_templates(card)
                        if tmpl_fields:
                            view_template_count += len(tmpl_fields)
                            result["template_heavy_cards"].append({
                                "dashboard": dash_name,
                                "view": view_title,
                                "type": card_type,
                                "title": card.get("title") or card.get("name") or "",
                                "fields_with_template": tmpl_fields,
                                "severity": "info",
                                "reason": (
                                    f"Jinja2 in: {', '.join(tmpl_fields)} — evaluated every time a related entity changes"
                                ),
                            })

                        # 4. DB query cards
                        if card_type in self._DB_QUERY_CARDS:
                            view_db_queries += 1
                            if card_type in ("history-graph", "statistics-graph"):
                                view_db_queries += len(self._extract_graph_entities(card))

                        # 5. Entity refs
                        card_entities = self._extract_all_entities(card)
                        for eid in card_entities:
                            view_entity_set.add(eid)
                            dash_entity_set.add(eid)
                            all_entity_refs_set.add(eid)
                            global_entity_counter[eid] = global_entity_counter.get(eid, 0) + 1

                    # ── Complexity score ──
                    complexity = self._compute_complexity(
                        card_count, view_max_depth,
                        len(view_entity_set), view_template_count,
                        view_db_queries, view_custom_count,
                    )
                    if complexity["score"] >= self.COMPLEXITY_WARN:
                        result["view_complexity"].append({
                            "dashboard": dash_name,
                            "view": view_title,
                            "severity": "critical" if complexity["score"] >= self.COMPLEXITY_CRITICAL else "warning",
                            **complexity,
                        })

                    per_view_entity_sets.append((dash_name, view_title, view_entity_set))
                    all_entity_refs_set.update(dash_entity_set)

                dashboard_summary.append({
                    "name": dash_name,
                    "views": len(views),
                    "cards": dash_card_count,
                    "heavy_cards": dash_heavy_count,
                    "entity_count": len(dash_entity_set),
                })

            # ── Post-process static checks ──
            result["missing_entities"] = sorted(
                eid for eid in all_entity_refs_set
                if "." in eid and eid not in all_state_ids
            )[:50]

            result["unavailable_entities"] = sorted(
                eid for eid in all_entity_refs_set
                if eid in unavail_states
            )[:50]

            result["duplicate_entities"] = sorted(
                [
                    {
                        "entity_id": eid,
                        "count": cnt,
                        "severity": "warning" if cnt <= 10 else "critical",
                        "reason": (
                            f"{eid} appears {cnt} times — consider using group or auto-entities"
                        ),
                    }
                    for eid, cnt in global_entity_counter.items()
                    if cnt > self.DUPLICATE_THRESHOLD
                ],
                key=lambda x: -x["count"],
            )[:30]

            # ── NEW #1 & #3: WebSocket pressure + Recorder cross-ref ──
            # Cả hai cần DB query → chỉ chạy nếu recorder available
            try:
                ws_pressure, recorder_xref = self._analyze_recorder_crossref(
                    all_entity_refs_set, per_view_entity_sets
                )
                result["ws_pressure"]     = ws_pressure
                result["recorder_crossref"] = recorder_xref
            except Exception as db_err:
                _LOGGER.debug("Dashboard recorder cross-ref skipped: %s", db_err)

            result["dashboards"]       = dashboard_summary
            result["total_entity_refs"] = len(all_entity_refs_set)
            result["summary"]          = self._build_summary(result)

        except Exception as exc:
            result["error"] = str(exc)
            _LOGGER.warning("DashboardAnalyzer error: %s", exc)

        return result

    # ------------------------------------------------------------------
    # NEW — Recorder cross-reference + WebSocket pressure (analysis #1 & #3)
    # ------------------------------------------------------------------
    def _analyze_recorder_crossref(
        self,
        dashboard_entities: set[str],
        per_view_entity_sets: list[tuple[str, str, set[str]]],
    ) -> tuple[list[dict], list[dict]]:
        """
        Query recorder để đo:
          1. writes/ngày và distinct_states cho mỗi entity trong dashboard
          2. Kết hợp → WebSocket push pressure + waste cross-ref

        Returns (ws_pressure_list, crossref_list)
        """
        from homeassistant.components.recorder import get_instance
        from sqlalchemy import text

        instance = get_instance(self.hass)
        db_url   = str(instance.engine.url)
        is_mysql = "mysql" in db_url or "mariadb" in db_url

        if is_mysql:
            ts_7d  = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 7 DAY))"
            ts_24h = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 24 HOUR))"
        else:
            ts_7d  = "strftime('%s', 'now', '-7 days')"
            ts_24h = "strftime('%s', 'now', '-24 hours')"

        if not dashboard_entities:
            return [], []

        # Build SQL IN clause — cap at 200 entities để tránh query quá dài
        sample = list(dashboard_entities)[:200]
        placeholders = ", ".join(f"'{e}'" for e in sample)

        ws_pressure:    list[dict] = []
        recorder_xref:  list[dict] = []

        with instance.get_session() as session:
            # Writes/ngày (avg over 7d) + distinct states (over 24h)
            rows = session.execute(text(f"""
                SELECT
                    entity_id,
                    ROUND(COUNT(*) / 7.0, 1)           AS writes_per_day,
                    COUNT(DISTINCT state)               AS distinct_states_7d
                FROM states
                WHERE last_updated_ts > {ts_7d}
                  AND entity_id IN ({placeholders})
                GROUP BY entity_id
                ORDER BY writes_per_day DESC
            """)).fetchall()

        # rows: [(entity_id, writes_per_day, distinct_states_7d), ...]
        entity_write_map: dict[str, tuple[float, int]] = {}
        for row in rows:
            eid = row[0]
            if not eid:
                continue
            wpd  = float(row[1] or 0)
            dist = int(row[2] or 1)
            entity_write_map[eid] = (wpd, dist)

        # Build reverse map: entity → which views contain it
        entity_to_views: dict[str, list[str]] = {}
        for dash_name, view_title, eset in per_view_entity_sets:
            for eid in eset:
                entity_to_views.setdefault(eid, []).append(f"{dash_name}/{view_title}")

        for eid, (wpd, dist) in entity_write_map.items():
            views_containing = entity_to_views.get(eid, [])

            # ── WebSocket pressure ──
            # Mỗi write → HA gửi state_changed event qua WebSocket đến browser
            if wpd >= self.WS_PUSH_WARNING:
                sev = "critical" if wpd >= self.WS_PUSH_CRITICAL else "warning"
                friendly = ""
                state_obj = self.hass.states.get(eid)
                if state_obj:
                    friendly = state_obj.attributes.get("friendly_name", "")
                ws_pressure.append({
                    "entity_id":     eid,
                    "name":          friendly or eid,
                    "writes_per_day": wpd,
                    "distinct_states": dist,
                    "in_views":      views_containing[:5],
                    "severity":      sev,
                    "description": (
                        f"{eid} updates {wpd:.0f} times/day → browser receives {wpd:.0f} WebSocket pushes/day ({dist} distinct values)"
                    ),
                    "suggestion": (
                        "Reduce integration polling, add throttle/filter, or exclude from recorder"
                    ) if dist <= 5 else (
                        "Check integration config to reduce polling interval"
                    ),
                })

            # ── Recorder cross-reference ──
            # Entity update nhiều nhưng ít distinct → ghi DB + push WebSocket lãng phí
            if wpd >= self.XREF_WRITES_WARNING and dist > 0:
                waste_ratio = wpd / max(dist, 1)
                if waste_ratio >= self.XREF_WASTE_RATIO:
                    state_obj = self.hass.states.get(eid)
                    friendly  = state_obj.attributes.get("friendly_name", "") if state_obj else ""
                    domain    = eid.split(".")[0]
                    recorder_xref.append({
                        "entity_id":      eid,
                        "name":           friendly or eid,
                        "domain":         domain,
                        "writes_per_day": wpd,
                        "distinct_states": dist,
                        "waste_ratio":    round(waste_ratio, 1),
                        "in_views":       views_containing[:5],
                        "severity":       "critical" if waste_ratio >= 50 else "warning",
                        "description": (
                            f"{eid}: {wpd:.0f} writes/day "
                            f"but only {dist} distinct values "
                            f"(waste ratio {waste_ratio:.0f}x)"
                        ),
                        "suggestion": (
                            f"Add to recorder exclude or increase filter threshold for integration '{domain}'. Dashboard still works if excluded from recorder."
                        ),
                        "yaml_snippet": (
                            f"recorder:\n"
                            f"  exclude:\n"
                            f"    entities:\n"
                            f"      - {eid}"
                        ),
                    })

        # Sort by severity then writes_per_day
        ws_pressure   = sorted(ws_pressure,   key=lambda x: (-int(x["severity"] == "critical"), -x["writes_per_day"]))[:30]
        recorder_xref = sorted(recorder_xref, key=lambda x: (-x["waste_ratio"]))[:30]

        return ws_pressure, recorder_xref

    # ------------------------------------------------------------------
    # NEW — View complexity scorer (analysis #2)
    # ------------------------------------------------------------------
    def _compute_complexity(
        self,
        card_count:      int,
        max_depth:       int,
        entity_count:    int,
        template_count:  int,
        db_queries:      int,
        custom_count:    int,
    ) -> dict:
        """
        Tính điểm phức tạp của một view.
        Điểm càng cao → view càng tốn tài nguyên browser khi render/update.

        Công thức (có trọng số thực nghiệm):
          score = cards*1 + depth*8 + entities*2 + templates*5 + db_queries*10 + customs*3
        """
        score = (
            card_count    * 1
            + max_depth   * 8
            + entity_count * 2
            + template_count * 5
            + db_queries  * 10
            + custom_count * 3
        )
        # Human-readable breakdown
        breakdown = []
        if card_count > 0:
            breakdown.append(f"{card_count} cards (+{card_count*1})")
        if max_depth > 2:
            breakdown.append(f"nesting depth {max_depth} (+{max_depth*8})")
        if entity_count > 0:
            breakdown.append(f"{entity_count} entity sub (+{entity_count*2})")
        if template_count > 0:
            breakdown.append(f"{template_count} templates (+{template_count*5})")
        if db_queries > 0:
            breakdown.append(f"{db_queries} DB queries (+{db_queries*10})")
        if custom_count > 0:
            breakdown.append(f"{custom_count} custom cards (+{custom_count*3})")

        return {
            "score":          score,
            "card_count":     card_count,
            "max_depth":      max_depth,
            "entity_count":   entity_count,
            "template_count": template_count,
            "db_queries":     db_queries,
            "custom_count":   custom_count,
            "breakdown":      " | ".join(breakdown),
            "label": (
                "🔴 Very complex" if score >= self.COMPLEXITY_CRITICAL
                else "🟡 Complex"
            ),
        }

    def _measure_depth(self, card: dict, current: int = 1) -> int:
        """Đo độ sâu lồng nhau tối đa của cây card."""
        if not isinstance(card, dict):
            return current
        max_d = current
        for key in ("cards", "card", "elements"):
            child = card.get(key)
            if isinstance(child, list):
                for c in child:
                    d = self._measure_depth(c, current + 1)
                    if d > max_d:
                        max_d = d
            elif isinstance(child, dict):
                d = self._measure_depth(child, current + 1)
                if d > max_d:
                    max_d = d
        return max_d

    # ------------------------------------------------------------------
    # Existing helpers (unchanged)
    # ------------------------------------------------------------------

    def _collect_top_level_cards(self, view: dict, out: list):
        out.extend(c for c in view.get("cards", []) if isinstance(c, dict))
        for section in view.get("sections", []):
            if isinstance(section, dict):
                out.extend(c for c in section.get("cards", []) if isinstance(c, dict))

    def _flatten_cards(self, card: dict, out: list):
        if not isinstance(card, dict):
            return
        out.append(card)
        for key in ("cards", "card"):
            child = card.get(key)
            if isinstance(child, list):
                for c in child:
                    self._flatten_cards(c, out)
            elif isinstance(child, dict):
                self._flatten_cards(child, out)
        for elem in card.get("elements", []):
            if isinstance(elem, dict):
                self._flatten_cards(elem, out)

    def _extract_all_entities(self, card: dict) -> list[str]:
        entities: set[str] = set()

        def _add(val):
            if isinstance(val, str) and "." in val and not val.startswith("{"):
                entities.add(val)

        _add(card.get("entity", ""))
        _add(card.get("camera_image", ""))
        for ent in card.get("entities", []):
            if isinstance(ent, str):
                _add(ent)
            elif isinstance(ent, dict):
                _add(ent.get("entity", ""))
        for feature in card.get("features", []):
            if isinstance(feature, dict):
                _add(feature.get("entity", ""))
        for cond in card.get("conditions", []):
            if isinstance(cond, dict):
                _add(cond.get("entity", ""))
        return list(entities)

    def _extract_graph_entities(self, card: dict) -> list[str]:
        entities: list[str] = []
        for ent in card.get("entities", []):
            if isinstance(ent, str) and "." in ent:
                entities.append(ent)
            elif isinstance(ent, dict):
                eid = ent.get("entity", "")
                if eid and "." in eid:
                    entities.append(eid)
        return entities

    def _detect_templates(self, card: dict) -> list[str]:
        found: list[str] = []
        for field in self._TEMPLATE_FIELDS:
            val = card.get(field)
            if isinstance(val, str) and ("{%" in val or "{{" in val):
                found.append(field)
        for style_key in ("card_mod", "style"):
            if style_key in card:
                found.append(style_key)
        return found

    def _get_registered_custom_cards(self, storage_dir: str) -> set[str]:
        import json, os
        known: set[str] = set()
        resource_file = os.path.join(storage_dir, "lovelace_resources")
        if os.path.exists(resource_file):
            try:
                with open(resource_file, encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("data", {}).get("items", []):
                    url      = item.get("url", "")
                    filename = url.rstrip("/").split("/")[-1].replace(".js", "")
                    if filename:
                        known.add(f"custom:{filename}")
            except Exception as e:
                _LOGGER.debug("Cannot read lovelace_resources: %s", e)
        frontend_file = os.path.join(storage_dir, "lovelace.hacs_dashboard")
        if os.path.exists(frontend_file):
            try:
                with open(frontend_file, encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("data", {}).get("config", {}).get("resources", []):
                    url      = item.get("url", "")
                    filename = url.rstrip("/").split("/")[-1].replace(".js", "")
                    if filename:
                        known.add(f"custom:{filename}")
            except Exception:
                pass
        return known

    def _build_summary(self, result: dict) -> dict:
        issues: list[dict] = []

        def _add(severity, category, count, label):
            if count > 0:
                issues.append({"severity": severity, "category": category,
                                "count": count, "label": label})

        c_heavy = sum(1 for c in result["heavy_cards"]    if c.get("severity") == "critical")
        w_heavy = sum(1 for c in result["heavy_cards"]    if c.get("severity") == "warning")
        _add("critical", "heavy_cards",       c_heavy, f"{c_heavy} critical heavy cards")
        _add("warning",  "heavy_cards",       w_heavy, f"{w_heavy} heavy cards")
        _add("critical", "overloaded_views",
             sum(1 for v in result["overloaded_views"] if v["severity"] == "critical"),
             "overloaded views (critical)")
        _add("warning",  "overloaded_views",
             sum(1 for v in result["overloaded_views"] if v["severity"] == "warning"),
             "overloaded views (warning)")
        _add("critical", "missing_entities",  len(result["missing_entities"]),       "entities not found in HA")
        _add("warning",  "unavailable_entities", len(result["unavailable_entities"]), "entities unavailable/unknown")
        _add("warning",  "duplicate_entities",len(result["duplicate_entities"]),     "entities duplicated >5 times")
        _add("warning",  "heavy_graphs",      len(result["heavy_graphs"]),           "graph cards with many entities")
        _add("warning",  "unconfigured_custom_cards", len(result["unconfigured_custom_cards"]), "custom cards not installed")
        _add("info",     "template_heavy_cards", len(result["template_heavy_cards"]), "cards with Jinja2 templates")
        # NEW
        _add("critical", "view_complexity",
             sum(1 for v in result["view_complexity"] if v["severity"] == "critical"),
             "views with critical complexity score")
        _add("warning",  "view_complexity",
             sum(1 for v in result["view_complexity"] if v["severity"] == "warning"),
             "views with high complexity score")
        _add("critical", "ws_pressure",
             sum(1 for w in result["ws_pressure"]     if w["severity"] == "critical"),
             "entities causing extreme WebSocket push")
        _add("warning",  "ws_pressure",
             sum(1 for w in result["ws_pressure"]     if w["severity"] == "warning"),
             "entities causing high WebSocket push")
        _add("critical", "recorder_crossref",
             sum(1 for r in result["recorder_crossref"] if r["severity"] == "critical"),
             "entities wasting DB + bandwidth (critical)")
        _add("warning",  "recorder_crossref",
             sum(1 for r in result["recorder_crossref"] if r["severity"] == "warning"),
             "entities wasting DB + bandwidth (warning)")

        total_critical = sum(1 for i in issues if i["severity"] == "critical")
        total_warning  = sum(1 for i in issues if i["severity"] == "warning")

        return {
            "issues":          issues,
            "total_critical":  total_critical,
            "total_warning":   total_warning,
            "dashboard_score": max(0, 100 - total_critical * 10 - total_warning * 4),
        }


# ================================================================
# STATE STORM DETECTOR
# ================================================================

class StateStormDetector:
    """Detects entities changing state abnormally fast."""

    # Expected max updates per hour by domain (rough baseline)
    DOMAIN_BASELINE = {
        "sensor":        60,   # most sensors: 1/min is already fast
        "binary_sensor": 30,
        "light":         20,
        "switch":        20,
        "climate":       12,
        "cover":         10,
        "media_player":  30,
        "input_boolean": 10,
        "input_number":  10,
        "weather":        4,
        "sun":            4,
        "zone":           6,
    }
    DEFAULT_BASELINE = 60  # fallback for unknown domains

    def __init__(self, hass):
        self.hass = hass

    async def async_analyze(self) -> dict:
        return await self.hass.async_add_executor_job(self._run)

    def _run(self) -> dict:
        result = {
            "storms": [],
            "summary": {},
            "error": None,
        }
        try:
            from homeassistant.components.recorder import get_instance
            from sqlalchemy import text

            instance = get_instance(self.hass)
            db_url = str(instance.engine.url)
            is_mysql = "mysql" in db_url or "mariadb" in db_url

            if is_mysql:
                ts_24h = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 24 HOUR))"
                ts_1h  = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 1 HOUR))"
                domain_expr = "SUBSTRING_INDEX(entity_id, '.', 1)"
            else:
                ts_24h = "strftime('%s', 'now', '-24 hours')"
                ts_1h  = "strftime('%s', 'now', '-1 hour')"
                domain_expr = "substr(entity_id, 1, instr(entity_id, '.') - 1)"

            with instance.get_session() as session:
                # Changes per entity in last 24h
                rows = session.execute(text(f"""
                    SELECT
                        entity_id,
                        COUNT(*) as changes_24h,
                        COUNT(DISTINCT state) as distinct_states
                    FROM states
                    WHERE last_updated_ts > {ts_24h}
                    GROUP BY entity_id
                    HAVING COUNT(*) > 20
                    ORDER BY COUNT(*) DESC
                    LIMIT 50
                """)).fetchall()

                # Changes in last 1h (for burst detection)
                rows_1h = session.execute(text(f"""
                    SELECT entity_id, COUNT(*) as changes_1h
                    FROM states
                    WHERE last_updated_ts > {ts_1h}
                    GROUP BY entity_id
                    ORDER BY COUNT(*) DESC
                    LIMIT 50
                """)).fetchall()
                changes_1h_map = {r[0]: r[1] for r in rows_1h if r[0]}

                storms = []
                for row in rows:
                    entity_id = row[0]
                    if not entity_id:
                        continue
                    changes_24h = row[1]
                    distinct_states = row[2]
                    changes_1h = changes_1h_map.get(entity_id, 0)

                    domain = entity_id.split(".")[0]
                    baseline_per_hour = self.DOMAIN_BASELINE.get(domain, self.DEFAULT_BASELINE)
                    baseline_24h = baseline_per_hour * 24

                    ratio = round(changes_24h / max(baseline_24h, 1), 1)
                    if ratio < 2.0:
                        continue  # not a storm

                    # Severity: warning if 2-5x, critical if >5x
                    if ratio >= 5:
                        severity = "critical"
                    elif ratio >= 2:
                        severity = "warning"
                    else:
                        continue

                    # Get current state from HA
                    state_obj = self.hass.states.get(entity_id)
                    current_state = state_obj.state if state_obj else "unknown"
                    friendly_name = state_obj.attributes.get("friendly_name", entity_id) if state_obj else entity_id
                    unit = state_obj.attributes.get("unit_of_measurement", "") if state_obj else ""

                    # Diagnosis
                    suggestions = []
                    if distinct_states <= 3:
                        suggestions.append("Value rarely changes but writes continuously — add a filter in the integration")
                    if domain == "sensor" and unit in ("°C", "°F", "%", "W", "V", "A"):
                        suggestions.append("Consider using 'entity_filter' or increase polling interval")
                    if changes_1h > baseline_per_hour * 3:
                        suggestions.append(f"Currently bursting: {changes_1h} times/hour")
                    suggestions.append("Add to recorder exclude to prevent DB bloat")

                    storms.append({
                        "entity_id": entity_id,
                        "name": friendly_name,
                        "domain": domain,
                        "changes_24h": changes_24h,
                        "changes_1h": changes_1h,
                        "baseline_24h": baseline_24h,
                        "ratio": ratio,
                        "distinct_states": distinct_states,
                        "current_state": f"{current_state} {unit}".strip(),
                        "severity": severity,
                        "suggestions": suggestions,
                    })

                result["storms"] = storms
                result["summary"] = {
                    "total_storms": len(storms),
                    "critical": sum(1 for s in storms if s["severity"] == "critical"),
                    "warning": sum(1 for s in storms if s["severity"] == "warning"),
                }

        except Exception as exc:
            result["error"] = str(exc)
            _LOGGER.warning("StateStormDetector error: %s", exc)
        return result


# ================================================================
# AUTOMATION DEAD CODE TRACER
# ================================================================

class AutomationDeadCodeTracer:
    """Finds automations with broken triggers, actions, or conditions."""

    def __init__(self, hass):
        self.hass = hass

    async def async_analyze(self) -> dict:
        return await self.hass.async_add_executor_job(self._run)

    def _run(self) -> dict:
        result = {
            "dead_automations": [],
            "total_analyzed": 0,
            "error": None,
        }
        try:
            import json, os, glob

            storage_dir = os.path.join(self.hass.config.config_dir, ".storage")
            auto_file = os.path.join(storage_dir, "core.automation")

            automations = []
            if os.path.exists(auto_file):
                with open(auto_file, encoding="utf-8") as f:
                    data = json.load(f)
                automations = data.get("data", {}).get("items", [])

            result["total_analyzed"] = len(automations)

            # All known entity_ids in HA right now
            existing = {s.entity_id for s in self.hass.states.async_all()}
            # Also include entities that exist in registry but might be disabled
            ent_reg = er.async_get(self.hass)
            registered = {e.entity_id for e in ent_reg.entities.values()}
            all_known = existing | registered

            dead = []
            for auto in automations:
                auto_id = auto.get("id", "")
                alias = auto.get("alias", auto_id)
                entity_id = f"automation.{alias.lower().replace(' ', '_')}"
                issues = []

                # --- Check triggers ---
                for i, trigger in enumerate(auto.get("trigger", []) or []):
                    t_issues = self._check_trigger(trigger, all_known, i)
                    issues.extend(t_issues)

                # --- Check conditions ---
                for i, cond in enumerate(auto.get("condition", []) or []):
                    c_issues = self._check_condition(cond, all_known, existing, i)
                    issues.extend(c_issues)

                # --- Check actions ---
                for i, action in enumerate(auto.get("action", []) or []):
                    a_issues = self._check_action(action, all_known, i)
                    issues.extend(a_issues)

                if issues:
                    dead.append({
                        "automation_id": auto_id,
                        "alias": alias,
                        "entity_id": entity_id,
                        "issues": issues,
                        "issue_count": len(issues),
                        "severity": "critical" if any(
                            i["type"] == "dead_trigger" for i in issues
                        ) else "warning",
                    })

            result["dead_automations"] = sorted(dead, key=lambda x: -x["issue_count"])

        except Exception as exc:
            result["error"] = str(exc)
            _LOGGER.warning("AutomationDeadCodeTracer error: %s", exc)
        return result

    def _check_trigger(self, trigger: dict, all_known: set, idx: int) -> list:
        issues = []
        t_type = trigger.get("platform", trigger.get("trigger", ""))

        if t_type in ("state", "numeric_state", "template"):
            entities = trigger.get("entity_id", [])
            if isinstance(entities, str):
                entities = [entities]
            for eid in entities:
                if eid and eid not in all_known:
                    issues.append({
                        "type": "dead_trigger",
                        "location": f"Trigger #{idx + 1}",
                        "description": f"Trigger entity does not exist: {eid}",
                        "entity": eid,
                    })

        elif t_type in ("device",):
            # Device triggers — check device still exists
            device_id = trigger.get("device_id")
            if device_id:
                dev_reg = dr.async_get(self.hass)
                if not dev_reg.async_get(device_id):
                    issues.append({
                        "type": "dead_trigger",
                        "location": f"Trigger #{idx + 1}",
                        "description": f"Device trigger: device_id '{device_id}' no longer exists",
                        "entity": device_id,
                    })
        return issues

    def _check_condition(self, cond: dict, all_known: set, existing: set, idx: int) -> list:
        issues = []
        c_type = cond.get("condition", "")

        if c_type in ("state", "numeric_state", "template"):
            entities = cond.get("entity_id", [])
            if isinstance(entities, str):
                entities = [entities]
            for eid in entities:
                if eid and eid not in all_known:
                    issues.append({
                        "type": "dead_condition",
                        "location": f"Condition #{idx + 1}",
                        "description": f"Condition entity does not exist: {eid}",
                        "entity": eid,
                    })
                elif eid and eid in existing:
                    # Check if entity is permanently unavailable
                    state = self.hass.states.get(eid)
                    if state and state.state == "unavailable":
                        issues.append({
                            "type": "always_false_condition",
                            "location": f"Condition #{idx + 1}",
                            "description": f"Entity is always 'unavailable': {eid} → condition always False",
                            "entity": eid,
                        })
        return issues

    def _check_action(self, action: dict, all_known: set, idx: int) -> list:
        issues = []
        action_type = action.get("action", action.get("service", ""))

        # Extract target entities
        target = action.get("target", {})
        target_entities = target.get("entity_id", [])
        if isinstance(target_entities, str):
            target_entities = [target_entities]

        # Also check data field for entity_id
        data = action.get("data", {})
        data_entities = data.get("entity_id", [])
        if isinstance(data_entities, str):
            data_entities = [data_entities]

        all_targets = list(target_entities) + list(data_entities)

        for eid in all_targets:
            if eid and eid not in all_known:
                issues.append({
                    "type": "dead_action",
                    "location": f"Action #{idx + 1}",
                    "description": f"Action target does not exist: {eid} (service: {action_type})",
                    "entity": eid,
                })

        # Check nested sequence/choose
        for key in ("sequence", "then", "else", "default"):
            nested = action.get(key, [])
            if isinstance(nested, list):
                for j, sub in enumerate(nested):
                    if isinstance(sub, dict):
                        issues.extend(self._check_action(sub, all_known, idx * 100 + j))

        for choice in action.get("choose", []):
            for sub in choice.get("sequence", []):
                issues.extend(self._check_action(sub, all_known, idx * 100))

        return issues


# ================================================================
# INTEGRATION HEALTH SCORE
# ================================================================

class IntegrationHealthAnalyzer:
    """
    Multi-criteria integration health analyzer.

    Scoring breakdown (100 points total):
      A) Connectivity   — unavailable/unknown events over 7 days       (max -35)
      B) Current state  — entities currently unavailable/unknown        (max -25)
      C) Config entry   — failed/retrying config entries                (max -15)
      D) Error spikes   — abnormal surge in last 24h vs baseline        (max -10)  [additive with A]

    Final score clamped to [0, 100]. Penalties are per-integration (weighted
    by ratio of affected entities to total entities in that integration).
    """

    def __init__(self, hass):
        self.hass = hass

    async def async_analyze(self) -> dict:
        return await self.hass.async_add_executor_job(self._run)

    def _run(self) -> dict:
        result = {
            "integrations": [],
            "problem_devices": [],
            "summary": {},
            "error": None,
        }
        try:
            from homeassistant.components.recorder import get_instance
            from sqlalchemy import text

            instance = get_instance(self.hass)
            db_url = str(instance.engine.url)
            is_mysql = "mysql" in db_url or "mariadb" in db_url

            if is_mysql:
                ts_7d  = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 7 DAY))"
                ts_24h = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 24 HOUR))"
                ts_1h  = "UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 1 HOUR))"
            else:
                ts_7d  = "strftime('%s', 'now', '-7 days')"
                ts_24h = "strftime('%s', 'now', '-24 hours')"
                ts_1h  = "strftime('%s', 'now', '-1 hour')"

            with instance.get_session() as session:
                # A) Connectivity: total unavailable/unknown events per entity, last 7d
                rows_7d = session.execute(text(f"""
                    SELECT entity_id, COUNT(*) as cnt
                    FROM states
                    WHERE last_updated_ts > {ts_7d}
                      AND state IN ('unavailable', 'unknown')
                    GROUP BY entity_id
                    ORDER BY cnt DESC
                    LIMIT 200
                """)).fetchall()
                unavail_7d = {r[0]: int(r[1]) for r in rows_7d if r[0]}

                # B) Current state snapshot — entities right now unavailable/unknown
                rows_cur = session.execute(text(f"""
                    SELECT entity_id, state
                    FROM states
                    WHERE last_updated_ts > {ts_1h}
                      AND state IN ('unavailable', 'unknown')
                    GROUP BY entity_id
                """)).fetchall()
                currently_unavail = {r[0]: r[1] for r in rows_cur if r[0]}

                # E) Spike detection: events in last 24h
                rows_24h = session.execute(text(f"""
                    SELECT entity_id, COUNT(*) as cnt
                    FROM states
                    WHERE last_updated_ts > {ts_24h}
                      AND state IN ('unavailable', 'unknown')
                    GROUP BY entity_id
                """)).fetchall()
                unavail_24h = {r[0]: int(r[1]) for r in rows_24h if r[0]}

                # Baseline avg per day (from 7d data)
                baseline_map = {
                    eid: round(cnt / 7.0, 1)
                    for eid, cnt in unavail_7d.items()
                }

                # Total entity count per platform (for ratio weighting)
                rows_total = session.execute(text("""
                    SELECT metadata_id, COUNT(*) as cnt
                    FROM states
                    GROUP BY metadata_id
                    LIMIT 1
                """)).fetchall()

            ent_reg = er.async_get(self.hass)
            dev_reg = dr.async_get(self.hass)

            # ── D) Config entry health ──────────────────────────────
            config_entry_issues: dict[str, dict] = {}   # platform -> {failed, retrying, loaded}
            for ce in self.hass.config_entries.async_entries():
                platform = ce.domain
                if platform not in config_entry_issues:
                    config_entry_issues[platform] = {
                        "failed": 0, "retrying": 0, "loaded": 0,
                        "failed_titles": [],
                    }
                state_str = str(ce.state).lower()
                if "fail" in state_str or "error" in state_str:
                    config_entry_issues[platform]["failed"] += 1
                    config_entry_issues[platform]["failed_titles"].append(ce.title)
                elif "retry" in state_str or "setup_retry" in state_str:
                    config_entry_issues[platform]["retrying"] += 1
                else:
                    config_entry_issues[platform]["loaded"] += 1

            # ── Build entity index per platform ────────────────────
            _skip_internal = {"", None, "group", "persistent_notification", "homeassistant"}
            platform_entities: dict[str, list] = {}
            for entry_obj in ent_reg.entities.values():
                platform = entry_obj.platform or "unknown"
                if platform in _skip_internal:
                    continue
                platform_entities.setdefault(platform, []).append(entry_obj)


            # ── Build integration_map ───────────────────────────────
            integration_map: dict[str, dict] = {}

            for platform, entities in platform_entities.items():
                total_entities = len(entities)

                # Per-entity metrics
                conn_issues = 0          # entities with any unavail event in 7d
                currently_down = 0       # entities currently unavailable/unknown
                reconnects_total = 0     # sum of all unavail events 7d
                spike_entities = 0       # entities with abnormal surge today
                problem_entities_list = []

                for entry_obj in entities:
                    eid = entry_obj.entity_id
                    reconnects_7d = unavail_7d.get(eid, 0)
                    today_cnt     = unavail_24h.get(eid, 0)
                    avg_per_day   = baseline_map.get(eid, 0)
                    cur_state     = currently_unavail.get(eid)
                    is_down_now   = cur_state is not None

                    if reconnects_7d > 0:
                        conn_issues += 1
                        reconnects_total += reconnects_7d

                    if is_down_now:
                        currently_down += 1

                    is_spike = today_cnt > max(avg_per_day * 3, 5) and today_cnt > 3
                    if is_spike:
                        spike_entities += 1

                    # Add to problem list if any issue (battery excluded from criteria)
                    has_issue = reconnects_7d > 2 or is_down_now or is_spike
                    if has_issue:
                        dev_name = eid
                        if entry_obj.device_id:
                            dev = dev_reg.async_get(entry_obj.device_id)
                            if dev:
                                dev_name = dev.name_by_user or dev.name or eid

                        state_now = self.hass.states.get(eid)
                        current_val = state_now.state if state_now else "?"

                        problem = {
                            "entity_id": eid,
                            "device_name": dev_name,
                            "platform": platform,
                            "reconnects_7d": reconnects_7d,
                            "reconnects_today": today_cnt,
                            "avg_per_day": avg_per_day,
                            "current_state": current_val,
                            "is_down_now": is_down_now,
                            "is_spike": is_spike,
                            "diagnosis": self._diagnose(
                                reconnects_7d, today_cnt,
                                avg_per_day, is_down_now
                            ),
                        }
                        problem_entities_list.append(problem)
                        if reconnects_7d > 10 or is_down_now or is_spike:
                            result["problem_devices"].append(problem)

                # ── D) Config entry issues for this platform ────────
                ce_info = config_entry_issues.get(platform, {})
                failed_entries   = ce_info.get("failed", 0)
                retrying_entries = ce_info.get("retrying", 0)
                failed_titles    = ce_info.get("failed_titles", [])

                # ── Score calculation ────────────────────────────────
                # Ratio of affected entities (caps penalty for large integrations)
                ratio = conn_issues / max(total_entities, 1)

                # A) Connectivity penalty: -35 max, scaled by ratio + absolute reconnect volume
                penalty_connectivity = 0
                if conn_issues > 0:
                    base = min(ratio * 35, 25)           # ratio-weighted, max 25
                    volume_bonus = min(reconnects_total / 20, 10)  # high volume adds up to 10
                    penalty_connectivity = round(base + volume_bonus)

                # B) Currently down penalty: -25 max
                down_ratio = currently_down / max(total_entities, 1)
                penalty_down = round(min(down_ratio * 40, 25))

                # C) Config entry penalty: -15 max
                penalty_config = min(failed_entries * 10 + retrying_entries * 4, 15)

                # E) Spike penalty: -10 max
                penalty_spike = min(spike_entities * 5, 10)

                total_penalty = (
                    penalty_connectivity
                    + penalty_down
                    + penalty_config
                    + penalty_spike
                )
                score = max(0, 100 - total_penalty)

                integration_map[platform] = {
                    "name": platform,
                    "health_score": score,
                    "status": (
                        "critical" if score < 40 else
                        "warning"  if score < 70 else
                        "good"
                    ),
                    # Metrics
                    "total_entities": total_entities,
                    "entities_with_issues": conn_issues,
                    "currently_unavailable": currently_down,
                    "total_reconnects_7d": reconnects_total,
                    "spike_entities": spike_entities,
                    "config_failed": failed_entries,
                    "config_retrying": retrying_entries,
                    "config_failed_titles": failed_titles,
                    # Score breakdown (for tooltip/detail view)
                    "score_breakdown": {
                        "connectivity": -penalty_connectivity,
                        "currently_down": -penalty_down,
                        "config_entry": -penalty_config,
                        "error_spike": -penalty_spike,
                    },
                    "problem_entities": problem_entities_list,
                }

            # ── Summary stats ────────────────────────────────────────
            all_scores = [ig["health_score"] for ig in integration_map.values()]
            result["summary"] = {
                "total_integrations": len(integration_map),
                "critical_count": sum(1 for s in all_scores if s < 40),
                "warning_count":  sum(1 for s in all_scores if 40 <= s < 70),
                "good_count":     sum(1 for s in all_scores if s >= 70),
                "avg_score":      round(sum(all_scores) / len(all_scores)) if all_scores else 100,
            }

            result["integrations"] = sorted(
                integration_map.values(),
                key=lambda x: (x["health_score"] >= 70, x["health_score"], x["name"])
            )

        except Exception as exc:
            result["error"] = str(exc)
            _LOGGER.warning("IntegrationHealthAnalyzer error: %s", exc)
        return result

    def _diagnose(
        self,
        reconnects_7d: int,
        today: int,
        avg_per_day: float,
        is_down_now: bool = False,
    ) -> list[str]:
        diag = []
        if is_down_now:
            diag.append("🔴 Hiện đang offline (unavailable/unknown)")
        if today > avg_per_day * 5 and today > 3:
            diag.append(f"⚡ Spike hôm nay: {today} lần (trung bình {avg_per_day}/ngày)")
        elif today > avg_per_day * 2 and today > 2:
            diag.append(f"⚠️ Cao hơn bình thường: {today} vs {avg_per_day}/ngày")
        if reconnects_7d > 50:
            diag.append("📶 Có thể nhiễu sóng hoặc thiết bị quá xa hub")
        elif reconnects_7d > 20:
            diag.append(f"📶 Mất kết nối {reconnects_7d} lần trong 7 ngày — kiểm tra tín hiệu")
        elif reconnects_7d > 5:
            diag.append(f"🔌 Không ổn định: {reconnects_7d} lần unavailable/7 ngày")
        if not diag:
            diag.append("✅ Hoạt động bình thường")
        return diag
