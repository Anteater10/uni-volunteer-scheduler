# CCPA Data Retention and Deletion Policy

## Purpose

<!-- TODO(copy) -- Hung refines legal language -->

This document outlines how the Volunteer Scheduler application handles California Consumer Privacy Act (CCPA) data access and deletion requests.

## Scope

<!-- TODO(copy) -- Hung refines legal language -->

This policy applies to all personal information collected and processed by the Volunteer Scheduler platform, including user profiles, signup records, notification history, and audit logs.

## Data Collected

| Category | Fields | Retention |
|----------|--------|-----------|
| User profile | name, email, phone, university_id | Until deletion request |
| Signups | slot, status, timestamp | Indefinite (anonymized on delete) |
| Audit logs | action, actor_id, timestamp | Indefinite (compliance requirement) |
| Notifications | type, subject, delivery status | Indefinite |

<!-- TODO(copy) -- Hung refines legal language for each category -->

## Retention Period

<!-- TODO(copy) -- Hung refines legal language -->

Personal data is retained for the duration of the user's account. Upon a CCPA deletion request, personal data is anonymized but historical records (signups, audit logs) are preserved for operational integrity and grant reporting.

## Access Requests

<!-- TODO(copy) -- Hung refines legal language -->

Admins can fulfill data access requests via **Admin > Users > CCPA Data Export**. The export includes:

1. User profile (name, email, university_id, role, created_at)
2. All signup records with event details
3. Audit log entries where the user was the actor
4. Notification history

The export is provided as a JSON file download.

## Deletion Requests

<!-- TODO(copy) -- Hung refines legal language -->

Admins can fulfill deletion requests via **Admin > Users > CCPA Delete Account**. The deletion process:

1. Requires a documented reason (minimum 5 characters)
2. Requires explicit confirmation ("I understand this is irreversible")
3. Anonymizes all PII fields:
   - `name` -> `[deleted]`
   - `email` -> `deleted-{uuid}@example.invalid`
   - `phone` -> `null`
   - `university_id` -> `null`
   - `password` -> invalidated
4. Sets `deleted_at` timestamp
5. Preserves signup records for analytics integrity
6. Preserves audit log entries for compliance
7. Records the deletion action in the audit log with reason

## Technical Implementation

- **Soft delete**: User rows are never hard-deleted. The `deleted_at` field marks the account as deleted.
- **PII anonymization**: All personally identifiable fields are overwritten with placeholder values.
- **Signup preservation**: Historical signup records remain intact for aggregate analytics (volunteer hours, attendance rates).
- **Audit trail**: Every CCPA action (export or delete) creates an audit log entry with the admin's identity, timestamp, and stated reason.

## Contact

<!-- TODO(copy) -- Hung adds contact information -->

For CCPA inquiries, contact the system administrator.
