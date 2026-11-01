"""Analytics-only SQL reads and namespace ordering shared by sink and publisher."""

import hashlib

from psycopg.rows import dict_row


def rows(tx, statement, parameters=()):
    with tx.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement, parameters)
        return cursor.fetchall()


def one(tx, statement, parameters=()):
    found = rows(tx, statement, parameters)
    return found[0] if found else None


def lock_key(namespace, purpose="sink"):
    return int.from_bytes(
        hashlib.sha256(f"analytics:{purpose}:{namespace}".encode()).digest()[:8], "big", signed=True
    )


def sink_lock(tx, namespace):
    tx.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key(namespace),))


def journal(tx, namespace, source):
    tx.execute(
        """INSERT INTO receipt_journal(namespace,topic,partition,offset_number)
                  VALUES (%s,%s,%s,%s)""",
        (namespace, source["topic"], source["partition"], source["offset_number"]),
    )
