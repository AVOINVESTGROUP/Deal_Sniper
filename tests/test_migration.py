from src.migration import is_known_schema_version


def test_migration_accepts_current_immutable_contracts_on_repeat_run() -> None:
    assert is_known_schema_version("verification-evidence/v1")
    assert is_known_schema_version("saved-search/v1")
    assert is_known_schema_version("outcome/v1")
    assert is_known_schema_version("publication-event/v1")
    assert is_known_schema_version("audit-event/v1")
    assert is_known_schema_version("migration-replay-request/v1")


def test_migration_still_blocks_unknown_contracts() -> None:
    assert not is_known_schema_version("unreviewed-schema/v1")
    assert is_known_schema_version("future-reviewed/v2")
