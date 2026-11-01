# M06 skip update: 1 November 2026

Source commit **54c5238**. Final host suite: **325 passed, 52 skipped**. Separate
Linux suite: **85 passed, 1 skipped**. **46 host skips passed in Linux**: 24 POSIX
filesystem cases, three M04 live cases, twelve M05 live cases and seven M06 live
cases. The six older infrastructure/transport live cases below were not rerun;
their earlier evidence is historical, not a current pass.

The Linux skip is the Windows-only directory-fsync rejection guard, which passed
on Windows. No skip marker hides a failure. Raw evidence is
artifacts/m06/{host-final,linux-final}.xml; every exact host skip, reason and Linux
coverage flag is recorded in artifacts/m06/skips.json. Notifications in the new
invalid-source tests use the explicit SQL outbox double. The full 100,000-record
W-QUALITY fixture, real shared outbox, catalogue verification and performance are
NOT_RUN, beyond these individual test skips.

New M06 host-skipped cases, all passed in Linux:

- tests.pipelines.test_silver_kafka_live.test_all_five_topics_have_durable_prefixes_and_one_effect_per_event
- tests.pipelines.test_silver_live.test_all_24_domains_unique_duplicate_redelivery_and_active_files
- tests.pipelines.test_silver_live.test_cross_type_versions_conflicts_and_out_of_order_valid_facts
- tests.pipelines.test_silver_live.test_sink_failure_rolls_back_only_failed_b0_record_and_can_resume
- tests.pipelines.test_silver_live.test_dead_letter_notices_never_enter_business_silver
- tests.pipelines.test_silver_live.test_utc_day_boundaries_and_canonical_facets_are_preserved
- tests.pipelines.test_silver_live.test_quality_ratio_smoke_with_all_ten_invalid_subcases

M05's formerly unsupported-TOOL_CALLED case is now named
test_tool_event_is_now_supported_without_dirty_classification and verifies its
accepted source, unique Silver row and active Gold count. The old case name below
belongs to the historical M05 checkpoint.

# M05 skip update: 1 November 2026

Final host suite: **298 passed, 45 skipped**. Separate source-pinned Linux suite: **51 passed, 1 skipped**. Of the host skips, **39 passed in Linux**: 24 filesystem cases, three M04 live cases and twelve M05 live cases. The remaining six older live cases were not rerun; their names/reasons and earlier real evidence remain in the historical report below.

The single Linux skip is the Windows-only directory-fsync rejection guard, which passed on Windows. No skip marker was added to hide a failure. Raw evidence: artifacts/m05/{host-final,linux-final}.xml and skips.json.

## New M05 host-skipped cases, all passed in Linux

- `tests.pipelines.test_vertical_kafka_live.test_native_sink_commit_before_offset_restart_and_invalid_backpressure`
- `tests.pipelines.test_vertical_live.test_real_valid_duplicate_redelivery_and_active_gold`
- `tests.pipelines.test_vertical_live.test_real_missing_outbox_leaves_invalid_source_pending`
- `tests.pipelines.test_vertical_live.test_real_quarantine_rollback_and_duplicate_identity_conflicts`
- `tests.pipelines.test_vertical_live.test_real_publication_disk_failure_preserves_pointer_and_pending`
- `tests.pipelines.test_vertical_live.test_real_postcommit_observation_failure_recovers_as_upper_bound`
- `tests.pipelines.test_vertical_publication_live.test_concurrent_arrival_survives_frozen_membership_and_stale_cas`
- `tests.pipelines.test_vertical_publication_live.test_single_publisher_and_bounded_snapshot`
- `tests.pipelines.test_vertical_publication_live.test_reader_pins_generation_reuses_untouched_files_and_checks_corruption`
- `tests.pipelines.test_vertical_publication_live.test_http_actual_manifest_gold_receipts_auth_and_readiness`
- `tests.pipelines.test_vertical_publication_live.test_other_event_type_backpressures_without_dirty_classification`
- `tests.pipelines.test_vertical_publication_live.test_pointer_transaction_failure_rolls_back_both_datasets`

Real SQL notification atomicity uses an explicitly labelled transactional outbox double. The separate missing-outbox and actual worker-runtime checks prove that absent Aditya code blocks malformed sources without advancing offsets. They do not prove real outbox integration or full G1. The M05 suite runs locally in Docker; it is not silently added to the shared GitHub workflow.

## Historical 2-MiB change report
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

All-domain Silver/Gold, actual shared-outbox integration, end-to-end G0/G1 and performance remain pending; M05 verifies one supported real valid-event slice. These are pending module/provider work, not passing tests and not hidden pytest skips. Successful fsync/process-restart tests do not prove hardware power-loss or volume-loss durability.

The shared GitHub workflow runs its existing Ubuntu/Windows/PostgreSQL checks. The new M04 capture suite was run locally in Docker; this report does not claim it is already wired into that shared workflow.
