# Fixtures

Place demo mailbox fixtures here as JSON files named `{fixture_id}.json`.

Minimum schema:

```json
{
  "fixture_id": "monday-chaos-v1",
  "messages": [
    {
      "message_id": "msg-001",
      "sender_name": "Casey Founder",
      "sender_email": "casey@example.com",
      "received_at": "2026-03-24T09:00:00Z",
      "subject": "Need approval by Wednesday",
      "body_text": "Please review the renewal today.",
      "headers": {
        "List-Unsubscribe": "<mailto:unsubscribe@example.com>"
      }
    }
  ]
}
```
