# Протокол четвёртой проверки плана от 25.07.2026

Статус: замечания включены в draft-документацию; план не утверждён, `0.11-STOP`
не выполнять, PR #1 не сливать.

## Блокирующие замечания проверки

1. Первый шаг STOP зависел от отсутствующего в текущем коде delivery feature flag.
2. Production migration могла выполняться кодом из ветки, которая ещё не стала воспроизводимым baseline.
3. `target_id` смешивал subject финансового решения и получателя доставки.
4. Operational verification timestamp менял fingerprint и мог создавать повторные решения и публикации.

## Внесённые изменения документации

- `0.11-STOP` использует только существующие инфраструктурные controls: publisher/Scheduler stop, queue pause, revoke secret access либо Telegram publishing permission и административный allowlist;
- application `delivery_enabled` реализуется в `0.11A` и проводится через Settings/Terraform в `0.11C`;
- добавлен `0.11RC` после приёмки `0.11A–0.11C`: фиксируются `release_candidate_commit`, `runtime_image_digest`, `migration_image_digest`, `schema_version` и `migration_tool_version`;
- staging и migration rehearsal выполняются только зафиксированными digest; любое изменение аннулирует RC;
- `0.11M` использует только digest из RC manifest, а `0.11D` делает `main` указателем ровно на тот же commit и продвигает тот же runtime digest;
- `decision_subject_id = listing_id`, `vehicle_id` используется для cross-source связи, `delivery_recipient_id` — только для адресата доставки;
- `market_fingerprint` содержит immutable semantic evidence, но не operational freshness, attempts или latency;
- повторная проверка неизменившейся evidence обновляет TTL, не меняя fingerprint, decision, delivery и публикацию.

## Канонический порядок

```text
0.11-STOP -> 0.11R -> 0.11A -> 0.11B -> 0.11C
          -> 0.11RC -> 0.11M -> 0.11D -> 0.11P -> 0.12+
```

Код, production, IAM, Scheduler, Cloud Tasks и данные этой редакцией не изменялись.
