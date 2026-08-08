CREATE TABLE IF NOT EXISTS "hashes" (
    "hash"	TEXT NOT NULL UNIQUE,
    "query"	TEXT NOT NULL,
    "ts"	INTEGER NOT NULL,
    PRIMARY KEY("hash")
);
