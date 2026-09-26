-- Transactional outbox. Canonical writes (gold publish, user state, admin edits)
-- insert an event in the same transaction; downstream (search, graph) consume later.
-- Source: docs/DATA_MODEL.md §11, docs/ARCHITECTURE.md §5.3.

CREATE TABLE outbox_event (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(50)  NOT NULL,        -- 'DRAMA', 'PERSON', 'USER_DRAMA_STATE', ...
    aggregate_id    VARCHAR(100) NOT NULL,
    event_type      VARCHAR(100) NOT NULL,        -- 'DRAMA_CANONICAL_UPDATED', ...
    payload         JSONB        NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ
);

-- Consumers poll unpublished events in insertion order.
CREATE INDEX idx_outbox_event_unpublished
    ON outbox_event (created_at) WHERE published_at IS NULL;
