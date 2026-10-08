# Architecture

The public repository specifies procedures. Cases keep their own private data.

Core layers: original sources, evidence catalog, search indexes, task board, and agent integrations.

Use local SQLite for a single-machine prototype. Distributed use needs a server-side transactional database and authorization.
