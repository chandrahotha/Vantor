# Purchase Order State Machine

Draft -> Approved -> Sent -> Received -> Invoiced -> Closed; Draft/Approved/Sent may transition to Cancelled only under explicit policy.

Approval and send must be serialized. Sending creates exactly one commitment.

Every transition requires an explicit command, preconditions, actor authority, audit event and concurrency rule.
