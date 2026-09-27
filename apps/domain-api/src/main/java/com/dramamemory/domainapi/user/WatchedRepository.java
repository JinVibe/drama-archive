package com.dramamemory.domainapi.user;

import com.dramamemory.domainapi.user.WatchedDtos.DramaRef;
import com.dramamemory.domainapi.user.WatchedDtos.DramaState;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class WatchedRepository {

    private static final String SELECT = """
            SELECT s.drama_id, s.status, s.rating, s.first_watched_year, s.updated_at,
                   d.slug, d.title_ko, b.code AS broadcaster_code, d.start_date
              FROM user_drama_state s
              JOIN drama d ON d.id = s.drama_id
              LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
            """;

    private final JdbcClient jdbc;

    public WatchedRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public boolean dramaIsPublished(long dramaId) {
        return jdbc.sql("SELECT 1 FROM drama WHERE id = :id AND status = 'PUBLISHED'")
                .param("id", dramaId)
                .query(Integer.class)
                .optional()
                .isPresent();
    }

    public DramaState upsert(UUID userId, long dramaId, String status, BigDecimal rating, Integer firstWatchedYear) {
        jdbc.sql("""
                        INSERT INTO user_drama_state (user_id, drama_id, status, rating, first_watched_year)
                        VALUES (:u, :d, :s, :r, :y)
                        ON CONFLICT (user_id, drama_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            rating = EXCLUDED.rating,
                            first_watched_year = EXCLUDED.first_watched_year
                        """)
                .param("u", userId).param("d", dramaId).param("s", status)
                .param("r", rating).param("y", firstWatchedYear)
                .update();
        emit(userId, dramaId, "USER_DRAMA_STATE_UPDATED", status);
        return find(userId, dramaId).orElseThrow();
    }

    public boolean delete(UUID userId, long dramaId) {
        int n = jdbc.sql("DELETE FROM user_drama_state WHERE user_id = :u AND drama_id = :d")
                .param("u", userId).param("d", dramaId)
                .update();
        if (n > 0) {
            emit(userId, dramaId, "USER_DRAMA_STATE_REMOVED", null);
        }
        return n > 0;
    }

    public Optional<DramaState> find(UUID userId, long dramaId) {
        return jdbc.sql(SELECT + " WHERE s.user_id = :u AND s.drama_id = :d")
                .param("u", userId).param("d", dramaId)
                .query((rs, i) -> map(rs))
                .optional();
    }

    public List<DramaState> list(UUID userId) {
        return jdbc.sql(SELECT + " WHERE s.user_id = :u ORDER BY s.updated_at DESC, s.drama_id DESC")
                .param("u", userId)
                .query((rs, i) -> map(rs))
                .list();
    }

    private static DramaState map(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new DramaState(
                new DramaRef(
                        rs.getLong("drama_id"),
                        rs.getString("slug"),
                        rs.getString("title_ko"),
                        rs.getString("broadcaster_code"),
                        rs.getObject("start_date", java.time.LocalDate.class)),
                rs.getString("status"),
                rs.getBigDecimal("rating"),
                rs.getObject("first_watched_year", Integer.class),
                rs.getObject("updated_at", OffsetDateTime.class));
    }

    private void emit(UUID userId, long dramaId, String eventType, String status) {
        jdbc.sql("""
                        INSERT INTO outbox_event (aggregate_type, aggregate_id, event_type, payload)
                        VALUES ('USER_DRAMA_STATE', :agg, :type,
                                jsonb_build_object('user_id', CAST(:u AS text), 'drama_id', CAST(:d AS bigint),
                                                   'status', CAST(:s AS text)))
                        """)
                .param("agg", userId + ":" + dramaId)
                .param("type", eventType)
                .param("u", userId.toString())
                .param("d", dramaId)
                .param("s", status)
                .update();
    }
}
