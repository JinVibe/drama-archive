-- User model per docs/DATA_MODEL.md §7 and docs/ADR/ADR-011-guest-first-auth.md.
-- Anonymous and logged-in users share app_user; user_identity presence tells them apart.

CREATE TABLE app_user (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name    VARCHAR(80),
    anonymous       BOOLEAN      NOT NULL DEFAULT true,
    status          VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    merged_into_id  UUID         REFERENCES app_user(id),
    last_active_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    upgraded_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT chk_app_user_status
        CHECK (status IN ('ACTIVE', 'MERGED', 'DELETED')),
    CONSTRAINT chk_app_user_merged_target
        CHECK ((status = 'MERGED') = (merged_into_id IS NOT NULL))
);

-- anonymous_user_cleanup DAG scans this (ADR-011 §6).
CREATE INDEX idx_app_user_anonymous_idle
    ON app_user (last_active_at) WHERE anonymous AND status = 'ACTIVE';

CREATE TRIGGER trg_app_user_updated_at
    BEFORE UPDATE ON app_user
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Social provider link. No profile image, email only with separate consent.
CREATE TABLE user_identity (
    user_id           UUID         NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    provider          VARCHAR(30)  NOT NULL,      -- 'kakao', 'naver', 'google', 'email'
    provider_subject  VARCHAR(255) NOT NULL,      -- provider-issued stable id
    email             VARCHAR(255),
    linked_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, provider_subject),
    UNIQUE (user_id, provider),

    CONSTRAINT chk_user_identity_provider
        CHECK (provider IN ('kakao', 'naver', 'google', 'apple', 'email'))
);

-- Consent log with the document version the user agreed to.
CREATE TABLE user_consent (
    user_id       UUID         NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    consent_type  VARCHAR(40)  NOT NULL,          -- 'TERMS', 'PRIVACY', 'AGE_14_PLUS', 'MARKETING'
    version       VARCHAR(20)  NOT NULL,
    granted       BOOLEAN      NOT NULL,
    recorded_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, consent_type, version),

    CONSTRAINT chk_user_consent_type
        CHECK (consent_type IN ('TERMS', 'PRIVACY', 'AGE_14_PLUS', 'MARKETING'))
);

-- 봤어요 / 보는 중 / 보고 싶어요 (PRD FR-06).
CREATE TABLE user_drama_state (
    user_id             UUID         NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    drama_id            BIGINT       NOT NULL REFERENCES drama(id),
    status              VARCHAR(30)  NOT NULL,
    rating              NUMERIC(2,1),
    first_watched_year  SMALLINT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, drama_id),

    CONSTRAINT chk_user_drama_state_status
        CHECK (status IN ('WATCHED', 'WATCHING', 'WANT_TO_WATCH')),
    CONSTRAINT chk_user_drama_state_rating
        CHECK (rating IS NULL OR (rating >= 0.5 AND rating <= 5.0)),
    CONSTRAINT chk_user_drama_state_year
        CHECK (first_watched_year IS NULL OR first_watched_year BETWEEN 1950 AND 2100)
);

CREATE INDEX idx_user_drama_state_drama ON user_drama_state (drama_id);

CREATE TRIGGER trg_user_drama_state_updated_at
    BEFORE UPDATE ON user_drama_state
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
