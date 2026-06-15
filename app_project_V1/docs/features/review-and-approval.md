# Review And Approval

Some tables can require review before changes are published. When review is enabled, submissions become change requests that another user must approve or reject.

## When Review Is Enabled

Review is enabled per table through the Delta table property `review_required=true`.

When this flag is set:

- the app shows a Review & Approve tab
- data-entry actions submit change requests instead of publishing directly
- the app stores submitted snapshots in staging tables until a reviewer acts on them

## Workflow

1. A user submits a change from the Data Entry workflow.
2. The app ensures metadata and staging objects exist.
3. The app stores the proposed snapshot in the table-specific staging table.
4. The app writes a metadata row to `app_metadata.change_requests`.
5. A reviewer opens the Review & Approve tab.
6. The reviewer inspects the staged rows and approves or rejects the request.
7. Approval publishes the staged snapshot; rejection keeps the audit trail and marks the request as rejected.

## Review Queue Features

Reviewers can filter requests by:

- status
- target table
- submitter

The review panel shows:

- change request metadata
- row count
- submitter and timestamps
- staged row contents
- approval and rejection actions for pending requests

## Approval Rules

- pending requests can be approved or rejected
- users cannot approve their own submissions
- users cannot reject their own submissions
- approved and rejected requests remain visible for audit purposes

## Backing Objects

The review workflow uses:

- `{catalog}.app_metadata.change_requests`
- `{target_table}_staging`

Operational details are documented in [../operations.md](../operations.md).

## Related Guides

- Data entry workflow: [data-entry-and-versioning.md](data-entry-and-versioning.md)
- Operations: [../operations.md](../operations.md)
- Troubleshooting: [../troubleshooting.md](../troubleshooting.md)