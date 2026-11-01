-- Publication observations locate original and duplicate deliveries by event identity.
CREATE INDEX source_receipts_event ON source_receipts(namespace,event_id)
    WHERE event_id IS NOT NULL;
