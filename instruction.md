On May 19, 2026, the weekly certificate rotation audit on pki-audit-02 stopped producing compliance evidence following a policy engine update performed by the Security Engineering team. The SOC2 evidence collector flagged the missing reconciliation artifact during the Monday morning compliance check, 36 hours after the expected collection window.

The cert-audit reconciliation pipeline on pki-audit-02 had been operating normally up to the point of the policy update. The intent was to transition the audit scope from its dry-run testing state into active rotation tracking. The changes were staged incrementally and the promotion was never fully completed. By the time the Sunday 02:00 UTC collection window opened, no new evidence had reached /var/lib/cert-audit/evidence/reconciliation.tsv and none has arrived since.

Although the policy update did not necessarily break any individual component on its own, the aggregate effect of the incomplete changes is that the reconciliation tool refuses to proceed. The /opt/cert-audit/bin/reconcile-certs.sh entrypoint validates the active audit scope before doing any work and will exit immediately if it detects anything other than rotation mode. The production rotation parameters — correct evidence directory, correct output format — live in /etc/cert-audit/rotation-scope.conf, but that file is not being sourced. A lab-environment overlay at /etc/cert-audit/overrides.d/lab-defaults.conf runs after the main configuration at /etc/cert-audit/audit.conf loads and silently re-applies the QA defaults, redirecting output to staging and forcing CSV format. The shared environment loader included by every entrypoint also assigns OUTPUT_FORMAT directly, which means even if the correct format had been established by the time it runs, it would be overwritten.

Additionally, during a prior hardening pass, the infrastructure team applied filesystem immutable attributes to the evidence directory to prevent accidental deletion. This attribute was never removed after the initial population, and now prevents the reconciliation tool from writing new artifacts.

From where the data is coming:
rotation-events.jsonl contains one JSON object per line with fields: event_id, cert_fingerprint, action, lag_hours, status, and timestamp.
cluster-certs.json is a JSON array of certificate objects with fields: cert_fingerprint, common_name, namespace, issuer, and not_after.

**Required deliverables** — after all fixes are in place, run `/opt/cert-audit/bin/reconcile-certs.sh` and ensure the following files exist with the schemas described below:
1. `/var/lib/cert-audit/evidence/reconciliation.tsv` — the reconciled tab-delimited compliance evidence (it must land in the evidence directory, not under /var/lib/cert-audit/staging/).
2. `/var/lib/cert-audit/evidence/audit-schema.json` — an exact byte-for-byte copy of `/opt/cert-audit/audit-schema.json`.
3. `/opt/cert-audit/attestation.json` — a JSON object with exactly three keys: `artifact`, `sha256`, `rows`.
4. `/opt/cert-audit/compliance-gate.json` — a JSON object with exactly two keys: `status`, `rows`.

The evidence directory at /var/lib/cert-audit/evidence has an immutable filesystem attribute that must be cleared before the pipeline can create any files there.

Processing rules for the reconciliation TSV:
Rotation events in rotation-events.jsonl should be deduplicated by event_id — when the same event_id appears more than once, only the first occurrence is counted. Any rotation event referencing a cert_fingerprint that does not appear in cluster-certs.json (after excluding certificates in the "decommissioned" namespace) must be discarded entirely. For each certificate fingerprint, compute the total number of qualifying rotation events, the mean lag_hours (rounded half-up to two decimal places), and the compliance percentage as the fraction of events with status "success" (rounded half-up to two decimal places). Output rows sorted by cert_fingerprint ascending. The TSV uses tab as delimiter and its header line reads exactly: `cert_fingerprint\tcommon_name\trotation_count\tavg_lag_hours\tcompliance_pct`. Amounts and rates must have exactly two decimal digits. Unix LF line endings only. The file must end with a trailing newline.

The attestation.json at /opt/cert-audit/attestation.json requires exactly three keys: `artifact` (absolute path string to the reconciliation TSV), `sha256` (lowercase hexadecimal SHA-256 digest of the reconciliation TSV bytes), and `rows` (integer count of data rows, excluding the header line).

The compliance-gate.json at /opt/cert-audit/compliance-gate.json requires exactly two keys: `status` (the string `"PASS"`) and `rows` (integer, must equal the rows value in attestation.json). The file must end with a trailing newline.

The full authoritative schema for all output artifacts is in `/opt/cert-audit/audit-schema.json`, which the pipeline also copies as a sidecar next to reconciliation.tsv.

**Example** — `{"artifact": "/var/lib/cert-audit/evidence/reconciliation.tsv", "sha256": "abc123...", "rows": 3}`

**Example** — `{"status": "PASS", "rows": 3}`
