-- 작품별 한 줄 추억 (PRD FR-07, DATA_MODEL §7). Private first: visibility stays PRIVATE
-- until report/blind/moderation exist; the column is here so that switch is a data change.

CREATE TABLE memory_note (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID         NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    drama_id           BIGINT       NOT NULL REFERENCES drama(id),
    body               TEXT         NOT NULL,
    visibility         VARCHAR(20)  NOT NULL DEFAULT 'PRIVATE',
    moderation_status  VARCHAR(30)  NOT NULL DEFAULT 'PENDING',
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- One note per user per drama for now (FR-07 "한 줄 추억").
    UNIQUE (user_id, drama_id),
    CONSTRAINT chk_memory_note_visibility
        CHECK (visibility IN ('PRIVATE', 'PUBLIC')),
    CONSTRAINT chk_memory_note_moderation
        CHECK (moderation_status IN ('PENDING', 'APPROVED', 'BLINDED')),
    CONSTRAINT chk_memory_note_body_length
        CHECK (char_length(body) BETWEEN 1 AND 500)
);

CREATE TRIGGER trg_memory_note_updated_at
    BEFORE UPDATE ON memory_note
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
