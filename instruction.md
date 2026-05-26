On May 21, 2026, the nightly log aggregation job on log-03 began failing silently following a configuration migration performed by the Platform team. Alerts were suppressed during a maintenance window and the failure went undetected until the following morning, when the on-call engineer found no updated metrics report in the expected location.

The log-03 pipeline had been operating normally up to the point of the migration. The intent was to promote the runtime configuration from its current debug state into production. The changeset was committed in parts and the promotion was never fully completed. By midnight, when the cleanup process ran, no new output had reached /var/lib/log-agg/output/aggregated.csv and none has reached it since.

Although the migration did not necessarily break any individual component on its own, the aggregate effect of the incomplete changes is that the pipeline refuses to proceed. The /app/bin/process_logs.sh entrypoint checks the active profile before doing any work and will exit immediately if it detects anything other than production mode. The production values — correct output directory, correct field separator — live in /etc/log-agg/prod.env, but that file is not being sourced. A vendor-supplied drop-in at /etc/log-agg/config.env.local runs after the main configuration loads and silently re-applies the old debug defaults, undoing any correct values that managed to load. The shared bootstrap included by every entrypoint also assigns the separator directly, which means even if the correct separator had been established by the time it runs, it would be overwritten.

From where the data is coming:
server_logs.csv has request_id, endpoint_id, method, response_ms, and status_code.
endpoints.csv has endpoint_id and name.

**Required deliverables** — after all fixes are in place, run `/app/bin/process_logs.sh` and ensure the following files exist with the schemas described below:
1. `/var/lib/log-agg/output/aggregated.csv` — the aggregated pipe-delimited output (it must land in the output directory, not under /var/lib/log-agg/staging/).
2. `/var/lib/log-agg/output/log-agg-contract.json` — an exact byte-for-byte copy of `/app/log-agg-contract.json`.
3. `/app/report.json` — a JSON object with exactly three keys: `artifact`, `sha256`, `rows`.
4. `/app/status.json` — a JSON object with exactly two keys: `status`, `rows`.

The output directory at /var/lib/log-agg/output will need write access before the pipeline can create any files there.

Processing rules for the aggregated CSV:
Entries in server_logs.csv should be deduplicated by request_id — when the same request_id appears more than once, only the first occurrence is counted. Any log entry referencing an endpoint_id that does not appear in endpoints.csv must be discarded entirely. For each endpoint, compute the total number of qualifying requests, the mean response_ms (rounded half-up to two decimal places), and the error rate as a percentage of requests with status_code 400 or higher (rounded half-up to two decimal places). Output rows sorted by endpoint_id ascending. The CSV uses pipe as delimiter and its header line reads exactly: `Endpoint ID|Endpoint Name|Total Requests|Avg Response Ms|Error Rate`. Amounts and rates must have exactly two decimal digits. Unix LF line endings only. The file must end with a trailing newline.

The report.json at /app/report.json requires exactly three keys: `artifact` (absolute path string to the aggregated CSV), `sha256` (lowercase hexadecimal SHA-256 digest of the aggregated CSV bytes), and `rows` (integer count of data rows, excluding the header line).

The status.json at /app/status.json requires exactly two keys: `status` (the string `"OK"`) and `rows` (integer, must equal the rows value in report.json). The file must end with a trailing newline.

The full authoritative schema for all output artifacts is in `/app/log-agg-contract.json`, which the pipeline also copies as a sidecar next to aggregated.csv.

**Example** — `{"artifact": "/var/lib/log-agg/output/aggregated.csv", "sha256": "abc123...", "rows": 3}`

**Example** — `{"status": "OK", "rows": 3}`
