package com.dramamemory.domainapi.user;

import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class UserRepository {

    /** last_active_at is only bumped when older than this, to avoid a write per request. */
    private static final Duration ACTIVITY_GRANULARITY = Duration.ofHours(1);

    private final JdbcClient jdbc;

    public UserRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public UUID createAnonymous() {
        return jdbc.sql("INSERT INTO app_user (anonymous) VALUES (true) RETURNING id")
                .query(UUID.class)
                .single();
    }

    /** Resolves a user id from a cookie, following MERGED rows to the survivor. */
    public Optional<CurrentUser> findActive(UUID id) {
        record Row(UUID id, boolean anonymous, String displayName, String status, UUID mergedInto) {}
        UUID cursor = id;
        for (int hops = 0; hops < 5 && cursor != null; hops++) {
            Optional<Row> row = jdbc.sql(
                            "SELECT id, anonymous, display_name, status, merged_into_id FROM app_user WHERE id = :id")
                    .param("id", cursor)
                    .query((rs, i) -> new Row(
                            rs.getObject("id", UUID.class),
                            rs.getBoolean("anonymous"),
                            rs.getString("display_name"),
                            rs.getString("status"),
                            rs.getObject("merged_into_id", UUID.class)))
                    .optional();
            if (row.isEmpty()) {
                return Optional.empty();
            }
            Row r = row.get();
            if ("ACTIVE".equals(r.status())) {
                return Optional.of(new CurrentUser(r.id(), r.anonymous(), r.displayName()));
            }
            cursor = "MERGED".equals(r.status()) ? r.mergedInto() : null;
        }
        return Optional.empty();
    }

    public void touch(UUID id) {
        jdbc.sql("""
                        UPDATE app_user SET last_active_at = now()
                         WHERE id = :id AND last_active_at < now() - CAST(:granularity AS interval)
                        """)
                .param("id", id)
                .param("granularity", ACTIVITY_GRANULARITY.toSeconds() + " seconds")
                .update();
    }
}
