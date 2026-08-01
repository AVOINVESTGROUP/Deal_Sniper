from __future__ import annotations

from dataclasses import dataclass

from src.migration import (
    MIGRATION_TOOL_VERSION,
    FirestoreMigrator,
    MigrationReport,
    is_known_schema_version,
)


@dataclass(frozen=True)
class FakeReference:
    path: str


class FakeDocument:
    def __init__(self, path: str, schema_version: object) -> None:
        self.reference = FakeReference(path)
        self._data = {"schema_version": schema_version}

    def to_dict(self) -> dict[str, object]:
        return dict(self._data)


class FakeCollection:
    def __init__(self, documents: list[FakeDocument]) -> None:
        self._documents = documents

    def stream(self) -> list[FakeDocument]:
        return list(self._documents)


class FakeBatch:
    def __init__(self, client: FakeClient) -> None:
        self._client = client
        self._pending_writes: list[tuple[str, dict[str, object], bool]] = []

    def set(
        self,
        reference: FakeReference,
        data: dict[str, object],
        *,
        merge: bool,
    ) -> None:
        self._pending_writes.append((reference.path, dict(data), merge))

    def commit(self) -> None:
        self._client.committed_writes.extend(self._pending_writes)
        self._client.commit_calls += 1
        self._pending_writes.clear()


class FakeClient:
    def __init__(
        self,
        collections: dict[str, list[FakeDocument]],
        collection_groups: dict[str, list[FakeDocument]] | None = None,
    ) -> None:
        self._collections = collections
        self._collection_groups = collection_groups or {}
        self.committed_writes: list[tuple[str, dict[str, object], bool]] = []
        self.commit_calls = 0

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self._collections.get(name, []))

    def collection_group(self, name: str) -> FakeCollection:
        return FakeCollection(self._collection_groups.get(name, []))

    def batch(self) -> FakeBatch:
        return FakeBatch(self)


def test_migration_accepts_current_immutable_contracts_on_repeat_run() -> None:
    assert is_known_schema_version("verification-evidence/v1")
    assert is_known_schema_version("saved-search/v1")
    assert is_known_schema_version("outcome/v1")
    assert is_known_schema_version("publication-event/v1")
    assert is_known_schema_version("publication-event/v3")
    assert is_known_schema_version("audit-event/v1")
    assert is_known_schema_version("migration-replay-request/v1")


def test_migration_still_blocks_unknown_contracts() -> None:
    assert not is_known_schema_version("unreviewed-schema/v1")
    assert not is_known_schema_version("unreviewed-schema/v3")
    assert not is_known_schema_version("publication-event/v4")
    assert is_known_schema_version("future-reviewed/v2")


def test_validation_path_accepts_publication_v3_and_blocks_other_unknown_versions() -> None:
    client = FakeClient(
        {
            "publication_events": [
                FakeDocument("publication_events/native-v3", "publication-event/v3"),
                FakeDocument("publication_events/arbitrary-v3", "unreviewed-schema/v3"),
                FakeDocument("publication_events/future-v4", "publication-event/v4"),
            ]
        },
        {
            "snapshots": [
                FakeDocument("listings/known/snapshots/v2", "listing-snapshot/v2"),
                FakeDocument("listings/unknown/snapshots/v3", "listing-snapshot/v3"),
            ]
        },
    )
    migrator = object.__new__(FirestoreMigrator)
    migrator.client = client  # type: ignore[assignment]
    report = MigrationReport(
        migration_id="migration-validation-test",
        dry_run=True,
        started_at="2026-07-31T00:00:00+00:00",
    )

    migrator._validate_known_schemas(report)

    assert report.unknown_schema == [
        "publication_events/arbitrary-v3=unreviewed-schema/v3",
        "publication_events/future-v4=publication-event/v4",
        "listings/unknown/snapshots/v3=listing-snapshot/v3",
    ]
    assert client.committed_writes == []
    assert client.commit_calls == 0


def test_top_level_upgrade_only_writes_legacy_schema_versions() -> None:
    native_schemas: list[object] = [
        "2",
        "listing-current/v2",
        "deal-decision/v2",
        "verification-evidence/v1",
        "saved-search/v1",
        "outcome/v1",
        "publication-event/v1",
        "publication-event/v3",
        "audit-event/v1",
        "migration-replay-request/v1",
    ]
    publication_documents = [
        FakeDocument("publication_events/legacy-none", None),
        FakeDocument("publication_events/legacy-v1", "1"),
        *[
            FakeDocument(f"publication_events/native-{index}", schema)
            for index, schema in enumerate(native_schemas)
        ],
    ]
    saved_search_documents = [
        FakeDocument("saved_searches/legacy-none", None),
        FakeDocument("saved_searches/native-v1", "saved-search/v1"),
    ]
    client = FakeClient(
        {
            "publication_events": publication_documents,
            "saved_searches": saved_search_documents,
        }
    )
    migrator = object.__new__(FirestoreMigrator)
    migrator.client = client  # type: ignore[assignment]
    report = MigrationReport(
        migration_id="migration-test",
        dry_run=False,
        started_at="2026-07-31T00:00:00+00:00",
    )

    migrator._upgrade_top_level_documents(report)

    assert [path for path, _data, _merge in client.committed_writes] == [
        "saved_searches/legacy-none",
        "publication_events/legacy-none",
        "publication_events/legacy-v1",
    ]
    assert all(
        data["schema_version"] == "2"
        for _path, data, _merge in client.committed_writes
    )
    assert all(
        data["migration_tool_version"] == "1.2.1"
        for _path, data, _merge in client.committed_writes
    )
    assert all(merge is True for _path, _data, merge in client.committed_writes)
    assert client.commit_calls == 2
    assert report.updated_counts["saved_searches"] == 1
    assert report.updated_counts["publication_events"] == 2
    assert sum(report.updated_counts.values()) == 3
    assert len(client.committed_writes) == 3


def test_migration_tool_version_is_bumped_for_compatibility_fix() -> None:
    assert MIGRATION_TOOL_VERSION == "1.2.1"
