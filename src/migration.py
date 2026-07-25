"""Идемпотентная миграция production Firestore к schema v2 без удаления истории."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from google.cloud import firestore

from src.domain.ids import canonical_hash, migration_id
from src.domain.models import ListingSnapshot
from src.storage import snapshot_hash

MIGRATION_TOOL_VERSION = "1.1.0"
TARGET_SCHEMA_VERSION = "2"
KNOWN_SCHEMA_VERSIONS = {None, "1", "2", "listing-current/v2", "deal-decision/v2"}


@dataclass(slots=True)
class MigrationReport:
    migration_id: str
    dry_run: bool
    started_at: str
    completed_at: str | None = None
    before_counts: dict[str, int] = field(default_factory=dict)
    after_counts: dict[str, int] = field(default_factory=dict)
    updated_counts: dict[str, int] = field(default_factory=dict)
    unknown_schema: list[str] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    collection_checksums: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    status: str = "running"


class FirestoreMigrator:
    """Schema-versioned writer; повторный запуск безопасен и сверяется с ledger."""

    COLLECTIONS = (
        "listings",
        "decisions",
        "notifications",
        "user_settings",
        "user_actions",
        "normalized_vehicles",
        "vehicle_identities",
        "raw_snapshots",
        "listing_current",
        "decision_current",
        "verification_evidence",
        "delivery_outbox",
        "saved_searches",
        "outcomes",
        "publication_events",
        "telegram_updates",
    )

    def __init__(self, project_id: str, database: str = "(default)") -> None:
        self.client = firestore.Client(project=project_id, database=database)

    def run(self, *, dry_run: bool, cutover_at: str, export_watermark: str) -> MigrationReport:
        watermark = datetime.fromisoformat(export_watermark.replace("Z", "+00:00"))
        stable_id = migration_id(
            f"legacy-v1@{cutover_at}:tool-{MIGRATION_TOOL_VERSION}",
            TARGET_SCHEMA_VERSION,
            watermark,
        )
        ledger = self.client.collection("migration_ledger").document(stable_id)
        existing = ledger.get().to_dict() or {}
        if existing.get("status") == "completed" and not dry_run:
            return MigrationReport(**existing["report"])
        report = MigrationReport(
            migration_id=stable_id,
            dry_run=dry_run,
            started_at=datetime.now(UTC).isoformat(),
        )
        report.before_counts = self._counts()
        report.collection_checksums = self._checksums()
        report.provenance = {
            "cutover_at": cutover_at,
            "export_watermark": export_watermark,
            "migration_tool_version": MIGRATION_TOOL_VERSION,
            "database": str(getattr(self.client, "_database", "(default)")),
        }
        report.checkpoints.append("inventory-complete")
        self._validate_known_schemas(report)
        if report.unknown_schema:
            report.status = "blocked_unknown_schema"
            self._finish(report, ledger)
            raise RuntimeError(
                "Обнаружены неизвестные schema_version: " + ", ".join(report.unknown_schema[:20])
            )
        report.checkpoints.append("schema-validation-complete")
        if not dry_run:
            self._rekey_snapshots_and_current(report)
            self._upgrade_top_level_documents(report)
            self._upgrade_nested_snapshots(report)
            self._close_legacy_notifications(report)
            self._invalidate_derived_state(report, cutover_at)
            self._prepare_replay_requests(report, stable_id)
            self._write_schema_ledger(stable_id, cutover_at, export_watermark)
            report.checkpoints.extend(
                [
                    "documents-upgraded",
                    "canonical-snapshots-rekeyed",
                    "nested-snapshots-upgraded",
                    "legacy-notifications-closed",
                    "derived-state-invalidated",
                    "replay-requests-prepared",
                    "schema-ledger-written",
                ]
            )
        report.after_counts = self._counts()
        report.status = "dry_run_complete" if dry_run else "completed"
        self._finish(report, ledger)
        return report

    def _counts(self) -> dict[str, int]:
        counts = {
            name: sum(1 for _document in self.client.collection(name).stream())
            for name in self.COLLECTIONS
        }
        counts["listing_snapshots"] = sum(
            1 for _document in self.client.collection_group("snapshots").stream()
        )
        return counts

    def _checksums(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for collection in self.COLLECTIONS:
            documents = [
                {
                    "path": item.reference.path,
                    "data": json.dumps(
                        item.to_dict() or {}, ensure_ascii=False, sort_keys=True, default=str
                    ),
                }
                for item in self.client.collection(collection).stream()
            ]
            result[collection] = canonical_hash(
                "firestore-collection-inventory/v1", {"documents": documents}
            )
        snapshots = [
            {
                "path": item.reference.path,
                "data": json.dumps(
                    item.to_dict() or {}, ensure_ascii=False, sort_keys=True, default=str
                ),
            }
            for item in self.client.collection_group("snapshots").stream()
        ]
        result["listing_snapshots"] = canonical_hash(
            "firestore-collection-inventory/v1", {"documents": snapshots}
        )
        return result

    def _validate_known_schemas(self, report: MigrationReport) -> None:
        for collection in self.COLLECTIONS:
            for document in self.client.collection(collection).stream():
                data = document.to_dict() or {}
                schema = data.get("schema_version")
                if schema not in KNOWN_SCHEMA_VERSIONS and not str(schema).endswith("/v2"):
                    report.unknown_schema.append(f"{document.reference.path}={schema}")
        for document in self.client.collection_group("snapshots").stream():
            schema = (document.to_dict() or {}).get("schema_version")
            if schema not in KNOWN_SCHEMA_VERSIONS and not str(schema).endswith("/v2"):
                report.unknown_schema.append(f"{document.reference.path}={schema}")

    def _upgrade_top_level_documents(self, report: MigrationReport) -> None:
        for collection in self.COLLECTIONS:
            batch = self.client.batch()
            operations = 0
            updated = 0
            for document in self.client.collection(collection).stream():
                data = document.to_dict() or {}
                schema = data.get("schema_version")
                if schema == "2" or str(schema).endswith("/v2"):
                    continue
                batch.set(
                    document.reference,
                    {
                        "schema_version": "2",
                        "migrated_at": firestore.SERVER_TIMESTAMP,
                        "migration_tool_version": MIGRATION_TOOL_VERSION,
                    },
                    merge=True,
                )
                operations += 1
                updated += 1
                if operations == 400:
                    batch.commit()
                    batch = self.client.batch()
                    operations = 0
            if operations:
                batch.commit()
            report.updated_counts[collection] = updated

    def _rekey_snapshots_and_current(self, report: MigrationReport) -> None:
        """Создаёт canonical v2 snapshot IDs и переводит current на точную новую версию."""
        batch = self.client.batch()
        operations = 0
        rekeyed = 0

        def flush_if_needed() -> None:
            nonlocal batch, operations
            if operations >= 390:
                batch.commit()
                batch = self.client.batch()
                operations = 0

        for document in self.client.collection_group("snapshots").stream():
            data = document.to_dict() or {}
            payload = data.get("payload")
            if not isinstance(payload, dict):
                continue
            canonical_content_hash = snapshot_hash(ListingSnapshot.model_validate(payload))
            if canonical_content_hash == document.id:
                continue
            canonical_reference = document.reference.parent.document(canonical_content_hash)
            batch.set(
                canonical_reference,
                {
                    **data,
                    "content_hash": canonical_content_hash,
                    "schema_version": "listing-snapshot/v2",
                    "migrated_from_content_hash": document.id,
                    "migrated_at": firestore.SERVER_TIMESTAMP,
                    "migration_tool_version": MIGRATION_TOOL_VERSION,
                },
                merge=False,
            )
            operations += 1
            rekeyed += 1
            flush_if_needed()

        for listing in self.client.collection("listings").stream():
            data = listing.to_dict() or {}
            payload = data.get("payload")
            if not isinstance(payload, dict):
                continue
            canonical_content_hash = snapshot_hash(ListingSnapshot.model_validate(payload))
            previous_hash = str(data.get("content_hash") or "")
            if canonical_content_hash != previous_hash:
                previous_reference = listing.reference.collection("snapshots").document(
                    previous_hash
                )
                if not previous_reference.get().exists:
                    canonical_reference = listing.reference.collection("snapshots").document(
                        canonical_content_hash
                    )
                    batch.set(
                        canonical_reference,
                        {
                            "payload": payload,
                            "content_hash": canonical_content_hash,
                            "schema_version": "listing-snapshot/v2",
                            "migrated_from_content_hash": previous_hash,
                            "migrated_at": firestore.SERVER_TIMESTAMP,
                            "migration_tool_version": MIGRATION_TOOL_VERSION,
                        },
                        merge=False,
                    )
                    operations += 1
                    flush_if_needed()
            batch.set(
                listing.reference,
                {
                    "content_hash": canonical_content_hash,
                    "lifecycle": data.get("lifecycle") or "active",
                    "schema_version": "listing-current/v2",
                    "migration_tool_version": MIGRATION_TOOL_VERSION,
                },
                merge=True,
            )
            operations += 1
            flush_if_needed()
        if operations:
            batch.commit()
        report.updated_counts["canonical_snapshot_rekeys"] = rekeyed

    def _upgrade_nested_snapshots(self, report: MigrationReport) -> None:
        batch = self.client.batch()
        operations = 0
        updated = 0
        for document in self.client.collection_group("snapshots").stream():
            data = document.to_dict() or {}
            schema = data.get("schema_version")
            if schema == "2" or str(schema).endswith("/v2"):
                continue
            batch.set(
                document.reference,
                {
                    "schema_version": "listing-snapshot/v2",
                    "migrated_at": firestore.SERVER_TIMESTAMP,
                    "migration_tool_version": MIGRATION_TOOL_VERSION,
                },
                merge=True,
            )
            operations += 1
            updated += 1
            if operations == 400:
                batch.commit()
                batch = self.client.batch()
                operations = 0
        if operations:
            batch.commit()
        report.updated_counts["listing_snapshots"] = updated

    def _invalidate_derived_state(
        self, report: MigrationReport, cutover_at: str
    ) -> None:
        targets = {
            "decision_current": {"migration_invalidated": True, "active": False},
            "normalized_vehicles": {"rebuild_required": True},
            "vehicle_identities": {"rebuild_required": True},
        }
        for collection, fields in targets.items():
            batch = self.client.batch()
            operations = 0
            updated = 0
            for document in self.client.collection(collection).stream():
                batch.set(
                    document.reference,
                    {
                        **fields,
                        "invalidated_at": cutover_at,
                        "migration_tool_version": MIGRATION_TOOL_VERSION,
                    },
                    merge=True,
                )
                operations += 1
                updated += 1
                if operations == 400:
                    batch.commit()
                    batch = self.client.batch()
                    operations = 0
            if operations:
                batch.commit()
            report.updated_counts[f"{collection}_invalidated"] = updated

    def _prepare_replay_requests(self, report: MigrationReport, stable_id: str) -> None:
        batch = self.client.batch()
        operations = 0
        prepared = 0
        for listing in self.client.collection("listings").stream():
            data = listing.to_dict() or {}
            content_hash = data.get("content_hash")
            if not content_hash:
                continue
            request_id = canonical_hash(
                "migration-replay-request/v1",
                {
                    "migration_id": stable_id,
                    "listing_id": listing.id,
                    "content_hash": content_hash,
                },
            )
            reference = self.client.collection("migration_replay_requests").document(request_id)
            batch.set(
                reference,
                {
                    "migration_id": stable_id,
                    "listing_id": listing.id,
                    "content_hash": content_hash,
                    "state": "pending",
                    "delivery_enabled": False,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "schema_version": "migration-replay-request/v1",
                },
                merge=False,
            )
            operations += 1
            prepared += 1
            if operations == 400:
                batch.commit()
                batch = self.client.batch()
                operations = 0
        if operations:
            batch.commit()
        report.updated_counts["migration_replay_requests"] = prepared

    def _close_legacy_notifications(self, report: MigrationReport) -> None:
        batch = self.client.batch()
        operations = 0
        for document in self.client.collection("notifications").stream():
            batch.set(
                document.reference,
                {
                    "legacy_closed": True,
                    "legacy_closed_at": firestore.SERVER_TIMESTAMP,
                    "replacement": "delivery_outbox/v2",
                },
                merge=True,
            )
            operations += 1
            if operations == 400:
                batch.commit()
                batch = self.client.batch()
                operations = 0
        if operations:
            batch.commit()

    def _write_schema_ledger(
        self, stable_id: str, cutover_at: str, export_watermark: str
    ) -> None:
        self.client.collection("schema_ledger").document("current").set(
            {
                "schema_version": TARGET_SCHEMA_VERSION,
                "migration_id": stable_id,
                "migration_tool_version": MIGRATION_TOOL_VERSION,
                "migration_cutover_at": cutover_at,
                "export_watermark": export_watermark,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "rollback_reader": "v1-compatible-top-level",
                "legacy_tasks_rejected_before": cutover_at,
            }
        )

    def _finish(
        self, report: MigrationReport, ledger: firestore.DocumentReference
    ) -> None:
        report.completed_at = datetime.now(UTC).isoformat()
        ledger.set(
            {
                "status": report.status,
                "report": asdict(report),
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
        )


def run_cli(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dubai Deal Sniper Firestore migration")
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--database", default=os.getenv("FIRESTORE_DATABASE", "(default)"))
    parser.add_argument("--cutover-at", default=os.getenv("MIGRATION_CUTOVER_AT", ""))
    parser.add_argument("--export-watermark", default=os.getenv("EXPORT_WATERMARK", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(arguments)
    if not args.project or not args.cutover_at or not args.export_watermark:
        parser.error("project, cutover-at и export-watermark обязательны")
    report = FirestoreMigrator(args.project, args.database).run(
        dry_run=args.dry_run,
        cutover_at=args.cutover_at,
        export_watermark=args.export_watermark,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
