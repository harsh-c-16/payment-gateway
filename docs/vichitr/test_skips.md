# Exact test skips: 2-MiB Bronze change

31 October 2026. No skip markers or assertions were disabled for this change.

Host run: **289 passed, 33 skipped**, 36.25 seconds. Linux run: **30 passed, 1 skipped**, 8.21 seconds. Raw JUnit evidence: artifacts/m04-2mib/{host-final,linux}.xml.

The separate shared-config regression run passed **34 tests, zero skips** (artifacts/m04-2mib/config.xml).

The earlier M04 host run had 31 skips: 22 Linux filesystem cases, three M04 live cases and six older live checks. Two new Linux boundary cases make the current host total 33. Of these, **27 passed in the separate Linux run**. The remaining **six were not rerun for this narrow cap change**; previous real evidence is identified below.

| Host-skipped cases | Count | Why / actual separate execution |
|---|---:|---|
| FileStore/Bronze cases in test_storage.py | 24 | Windows cannot provide required directory fsync. All 24 passed on the real Linux named volume, including both new size-boundary cases. |
| Capture integration in test_storage_live.py | 3 | Opt-in real Linux volume/Kafka/PostgreSQL checks, excluded from the host invocation. All three passed in Docker with RUN_STORAGE_LIVE_TESTS=1. |
| Registry compatibility in test_event_contracts_live.py | 1 | Separate opt-in registry/schema-evolution check; code unchanged. Not rerun for this cap change. Previous real pass: artifacts/m03/live-history-verified.xml. |
| Isolation/recreation in test_postgres_live.py | 1 | Separate Docker profile switches PostgreSQL to the original 2-GiB allocation and recreates its container. Not rerun for this size-only change. Previous real pass: artifacts/m01a/docker-live-20261031.xml. |
| Retention/groups in test_streaming_live.py | 1 | Recreates Kafka/registry containers to test retained data; kept separate from live capture tests. Not rerun for this cap change. Previous real pass: artifacts/m01b/live-verified.xml. |
| SDK/outbox-savepoint/rebalance in test_transport_live.py | 3 | Separate broker-pause, worker-rebalance and caller-SQL tests; transport code unchanged. Not rerun for this cap change. Previous real pass: artifacts/m03/live-history-verified.xml. Its outbox is explicitly a test double. |

The Linux-only run skipped **test_native_windows_fails_before_writing** because it checks unsupported native Windows behavior. That same case **passed in the host run**.

## Every host-skipped test

### Real Kafka/registry required; RUN_CONTRACTS_LIVE_TESTS=1

Count: 1; passed separately in Linux: 0.

- `tests.pipelines.test_event_contracts_live.test_registry_compatibility_and_all_domain_wire_examples`

### Real Docker required; opt in with RUN_POSTGRES_LIVE_TESTS=1

Count: 1; passed separately in Linux: 0.

- `tests.pipelines.test_postgres_live.test_real_isolation_and_persistence_across_container_recreation`

### Real Linux volume required; no fake Windows durability

Count: 24; passed separately in Linux: 24.

- `tests.pipelines.test_storage.test_opaque_archive_hash_idempotency_and_orphan_inventory`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[../escape]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[/absolute]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[a/../b]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[a//b]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[a/./b]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[C:/drive]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[a\\b]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[.filestore.lock]`
- `tests.pipelines.test_storage.test_paths_cannot_escape_or_address_internal_lock[]`
- `tests.pipelines.test_storage.test_symlink_escape_rejected`
- `tests.pipelines.test_storage.test_concurrent_writers_cannot_replace_immutable_winner`
- `tests.pipelines.test_storage.test_directory_fsync_failure_after_rename_is_visible_and_retryable`
- `tests.pipelines.test_storage.test_disk_full_before_rename_never_returns_capture_or_offsets`
- `tests.pipelines.test_storage.test_file_fsync_failure_leaves_no_completed_file`
- `tests.pipelines.test_storage.test_process_crash_after_rename_leaves_recoverable_orphan`
- `tests.pipelines.test_storage.test_exact_bytes_headers_nulls_coordinates_and_timestamps_round_trip`
- `tests.pipelines.test_storage.test_capture_is_not_a_final_disposition_or_commit_authorization`
- `tests.pipelines.test_storage.test_fixed_size_and_time_flushes_are_independent_of_sink_batching`
- `tests.pipelines.test_storage.test_capture_limits_and_raw_corruption_do_not_become_dirty_records`
- `tests.pipelines.test_storage.test_one_mib_raw_source_fits_after_base64_expansion`
- `tests.pipelines.test_storage.test_two_mib_encoded_boundary_includes_escaped_header_metadata`
- `tests.pipelines.test_storage.test_receipt_hash_locator_and_membership_tampering_are_detected`
- `tests.pipelines.test_storage.test_restart_preserves_files_and_reports_unreferenced_capture_without_cleanup`

### RUN_STORAGE_LIVE_TESTS=1 requires the Linux storage-check container and real services

Count: 3; passed separately in Linux: 3.

- `tests.pipelines.test_storage_live.test_real_sql_rollback_redelivery_conflict_and_restart_receipts`
- `tests.pipelines.test_storage_live.test_real_migration_drift_is_rejected`
- `tests.pipelines.test_storage_live.test_real_kafka_capture_sql_does_not_advance_offsets`

### Real Kafka/registry required; RUN_STREAMING_LIVE_TESTS=1

Count: 1; passed separately in Linux: 0.

- `tests.pipelines.test_streaming_live.test_plain_json_registry_groups_and_retained_volume_recreation`

### Real Kafka/PostgreSQL required; RUN_TRANSPORT_LIVE_TESTS=1

Count: 3; passed separately in Linux: 0.

- `tests.pipelines.test_transport_live.test_real_sdk_acknowledgement_manual_offsets_and_uncertain_retry`
- `tests.pipelines.test_transport_live.test_real_caller_transaction_and_outbox_savepoint_rollback`
- `tests.pipelines.test_transport_live.test_real_rebalance_fences_old_owner_and_redelivers_exact_source`

## Checks not claimed

Full Silver/Gold, actual shared-outbox integration, end-to-end G0/G1 and performance are not implemented/verified yet. These are pending module/provider work, not passing tests and not hidden pytest skips. Successful fsync/process-restart tests do not prove hardware power-loss or volume-loss durability.

The shared GitHub workflow runs its existing Ubuntu/Windows/PostgreSQL checks. The new M04 capture suite was run locally in Docker; this report does not claim it is already wired into that shared workflow.
