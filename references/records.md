# Record and history contract

Input is a JSON array of observations or a JSONL file with one observation per line. See [the fictional example](../examples/opportunities.example.json) and [schema](../schemas/opportunity.schema.json).

Required fields describe identity, channel, status, benefit, eligibility, costs/rights, source deadline text, primary URLs, application instructions/access, evidence level, limitations and next action. Use explicit unknowns rather than invented details. `application_url` may be null for an official email or announcement-based procedure.

`evidence` maps source URLs to supported field names. Source facts and personal eligibility are different. `recommended: false` can retain a verified but unsuitable item without putting it in the main list.

## Stable identity

If `id` is absent, the helper derives it from whitespace-normalized, Unicode-normalized, case-folded `organizer`, `program`, `edition`. Keep these canonical names consistent; automatic translation/entity matching is not provided. An explicit imported `id` is retained. A new round/year gets a new identity.

## Time and changes

- `last_checked_at`: actual observation timestamp including its timezone. The helper fills the current time only when the agent did not supply it.
- `first_seen_at`: preserved when updating history; a newly discovered item is not necessarily newly published.
- `change`: `new`, `updated`, or `unchanged`. Only material record changes count; a new check timestamp, evidence ordering or agent annotations alone do not.
- Unknown/custom fields on existing records are retained. New custom fields can be added. Unmentioned old records stay in history but not in this run's main list.

The deadline field preserves the source wording. This tool does not parse arbitrary deadlines or decide whether a page is still open; the researching assistant must set status using current evidence. The report displays the last check and its limitations, including when imported observations are older.

## Local files

The helper writes only inside the explicitly selected workspace:

```text
radar-data/
  opportunities.jsonl
  .state.lock
  runs/<unique-run>/
    digest.md
    observations.json
    receipt.json
```

State replacement is atomic. The operating system releases the write lock when the process exits. Every run has a separate report, so a repeat run does not overwrite earlier reports. A fictional demo is marked in both records and report and cannot be mixed into a real workspace by the helper.

If Python is unavailable, an assistant may use accessible files or connected documents while preserving IDs, prior notes, original check times and the separation of current observations from old history. If storage is unavailable, deliver JSON to the user and describe the run as one-off. Do not pretend the chat itself guarantees durable storage.
