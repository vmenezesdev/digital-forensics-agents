# Coordination protocol v0 (draft)

The message board organizes work; it does not establish evidentiary facts.

Each task has a stable ID, status, owner, lease token, lease expiry, and version. Claims must be atomic. Stale tokens must not complete reassigned tasks. Messages retain author and task reference and must not be treated as reviewed findings.

Local agents coordinate through one SQLite database on one machine. A distributed version requires a server and authenticated identities. Task completion is not human review.
