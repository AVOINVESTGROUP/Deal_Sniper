# Протокол полного сквозного аудита плана от 25.07.2026

Статус: три оставшихся замечания включены в draft-документацию; план не утверждён,
`0.11-STOP` не выполнять, PR #1 не сливать.

## Блокирующие замечания

1. `0.11RC` должен был собрать migration image до реализации migration tooling.
2. `0.11M` возобновлял production до привязки `main` и runtime digest в `0.11D`.
3. Freshness проверялась по immutable времени создания evidence вместо отдельного `valid_until`.

## Внесённые изменения

- добавлен `0.11MI` до `0.11RC`: в нём реализуются schema readers/writers, migration plan, rebuild/invalidation, notification/task handling, dry-run, checkpoints, reconciliation, raw replay и rollback boundary;
- `0.11RC` выполняется только после приёмки `0.11MI` и замораживает уже реализованный migration image;
- `0.11M` не меняет код и исполняет только утверждённые RC digests; после migration/catch-up production остаётся stopped/maintenance-only с `delivery_enabled=false`;
- `0.11D` привязывает `main` к точному RC commit, развёртывает тот же runtime digest, проверяет `/version` и только затем выполняет staged resume collectors → processing → delivery;
- semantic evidence хранит неизменяемый `evidence_created_at`, operational freshness хранит `last_checked_at`, `valid_until` и `freshness_status`;
- verified market допускает только `verified`, `freshness_status=active`, `valid_until > now`; refresh той же evidence продлевает freshness без нового fingerprint, decision или delivery.

## Канонический порядок

```text
0.11-STOP -> 0.11R -> 0.11A -> 0.11B -> 0.11C
          -> 0.11MI -> 0.11RC -> 0.11M -> 0.11D -> 0.11P -> 0.12+
```

Код, production, IAM, Scheduler, Cloud Tasks и данные этой редакцией не изменялись.
