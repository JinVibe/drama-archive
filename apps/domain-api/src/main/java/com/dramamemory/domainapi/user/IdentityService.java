package com.dramamemory.domainapi.user;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Links a social identity to the current (usually anonymous) user — ADR-011 §1, §4, §7.
 *
 * <p>The OAuth dance itself lives in the provider callback (added once provider apps
 * are registered). This service is what the callback calls after it has verified
 * the provider subject.
 */
@Service
public class IdentityService {

    public record Consent(String type, String version, boolean granted) {}

    public record LinkResult(UUID userId, boolean merged) {}

    private final JdbcClient jdbc;

    public IdentityService(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Attach {@code provider/subject} to {@code currentUserId}. If that identity already
     * belongs to another account, the current account's records move there (newer
     * updated_at wins per drama) and the current account is marked MERGED.
     *
     * @return the user id the session cookie must now point at
     */
    @Transactional
    public LinkResult link(UUID currentUserId, String provider, String subject, String email,
            String displayName, List<Consent> consents) {
        Optional<UUID> existing = jdbc.sql("""
                        SELECT user_id FROM user_identity
                         WHERE provider = :p AND provider_subject = :s
                        """)
                .param("p", provider)
                .param("s", subject)
                .query(UUID.class)
                .optional();

        if (existing.isPresent() && !existing.get().equals(currentUserId)) {
            UUID target = existing.get();
            mergeInto(currentUserId, target);
            recordConsents(target, consents);
            return new LinkResult(target, true);
        }

        if (existing.isEmpty()) {
            jdbc.sql("""
                            INSERT INTO user_identity (user_id, provider, provider_subject, email)
                            VALUES (:u, :p, :s, :e)
                            """)
                    .param("u", currentUserId)
                    .param("p", provider)
                    .param("s", subject)
                    .param("e", email)
                    .update();
        }
        jdbc.sql("""
                        UPDATE app_user
                           SET anonymous = false,
                               upgraded_at = COALESCE(upgraded_at, now()),
                               display_name = COALESCE(display_name, :name)
                         WHERE id = :u
                        """)
                .param("u", currentUserId)
                .param("name", displayName)
                .update();
        recordConsents(currentUserId, consents);
        return new LinkResult(currentUserId, false);
    }

    private void mergeInto(UUID source, UUID target) {
        // Drama states: insert missing, and let the newer row win where both exist.
        jdbc.sql("""
                        INSERT INTO user_drama_state
                            (user_id, drama_id, status, rating, first_watched_year, created_at, updated_at)
                        SELECT :target, drama_id, status, rating, first_watched_year, created_at, updated_at
                          FROM user_drama_state WHERE user_id = :source
                        ON CONFLICT (user_id, drama_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            rating = EXCLUDED.rating,
                            first_watched_year = EXCLUDED.first_watched_year,
                            updated_at = EXCLUDED.updated_at
                        WHERE user_drama_state.updated_at < EXCLUDED.updated_at
                        """)
                .param("source", source)
                .param("target", target)
                .update();
        jdbc.sql("DELETE FROM user_drama_state WHERE user_id = :source").param("source", source).update();
        jdbc.sql("""
                        UPDATE app_user SET status = 'MERGED', merged_into_id = :target
                         WHERE id = :source
                        """)
                .param("source", source)
                .param("target", target)
                .update();
        jdbc.sql("""
                        INSERT INTO outbox_event (aggregate_type, aggregate_id, event_type, payload)
                        VALUES ('APP_USER', :source, 'USER_MERGED',
                                jsonb_build_object('source', :source, 'target', :target))
                        """)
                .param("source", source.toString())
                .param("target", target.toString())
                .update();
    }

    private void recordConsents(UUID userId, List<Consent> consents) {
        for (Consent c : consents) {
            jdbc.sql("""
                            INSERT INTO user_consent (user_id, consent_type, version, granted)
                            VALUES (:u, :t, :v, :g)
                            ON CONFLICT (user_id, consent_type, version) DO UPDATE SET
                                granted = EXCLUDED.granted, recorded_at = now()
                            """)
                    .param("u", userId)
                    .param("t", c.type())
                    .param("v", c.version())
                    .param("g", c.granted())
                    .update();
        }
    }
}
