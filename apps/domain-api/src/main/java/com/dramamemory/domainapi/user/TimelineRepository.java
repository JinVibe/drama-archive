package com.dramamemory.domainapi.user;

import com.dramamemory.domainapi.user.WatchedDtos.Timeline;
import com.dramamemory.domainapi.user.WatchedDtos.Timeline.ActorCount;
import com.dramamemory.domainapi.user.WatchedDtos.Timeline.BroadcasterCount;
import com.dramamemory.domainapi.user.WatchedDtos.Timeline.CodeCount;
import com.dramamemory.domainapi.user.WatchedDtos.Timeline.YearCount;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** Aggregates for /my/timeline (PRD FR-08). Counts are over WATCHED dramas unless noted. */
@Repository
public class TimelineRepository {

    private final JdbcClient jdbc;

    public TimelineRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Timeline build(UUID userId) {
        Map<String, Long> byStatus = new LinkedHashMap<>(Map.of("WATCHED", 0L, "WATCHING", 0L, "WANT_TO_WATCH", 0L));
        jdbc.sql("SELECT status, count(*) FROM user_drama_state WHERE user_id = :u GROUP BY status")
                .param("u", userId)
                .query((rs, i) -> Map.entry(rs.getString(1), rs.getLong(2)))
                .list()
                .forEach(e -> byStatus.put(e.getKey(), e.getValue()));

        List<YearCount> byYear = jdbc.sql("""
                        SELECT EXTRACT(YEAR FROM d.start_date)::int AS year, count(*)
                          FROM user_drama_state s JOIN drama d ON d.id = s.drama_id
                         WHERE s.user_id = :u AND s.status = 'WATCHED' AND d.start_date IS NOT NULL
                         GROUP BY 1 ORDER BY 1 DESC
                        """)
                .param("u", userId)
                .query((rs, i) -> new YearCount(rs.getInt(1), rs.getLong(2)))
                .list();

        List<BroadcasterCount> byBroadcaster = jdbc.sql("""
                        SELECT b.code, b.name_ko, count(*)
                          FROM user_drama_state s
                          JOIN drama d ON d.id = s.drama_id
                          JOIN broadcaster b ON b.id = d.broadcaster_id
                         WHERE s.user_id = :u AND s.status = 'WATCHED'
                         GROUP BY b.id ORDER BY 3 DESC, b.id
                        """)
                .param("u", userId)
                .query((rs, i) -> new BroadcasterCount(rs.getString(1), rs.getString(2), rs.getLong(3)))
                .list();

        List<CodeCount> byGenre = jdbc.sql("""
                        SELECT g.code, count(*)
                          FROM user_drama_state s
                          JOIN drama_genre dg ON dg.drama_id = s.drama_id
                          JOIN genre g ON g.id = dg.genre_id
                         WHERE s.user_id = :u AND s.status = 'WATCHED'
                         GROUP BY g.id ORDER BY 2 DESC, g.code
                        """)
                .param("u", userId)
                .query((rs, i) -> new CodeCount(rs.getString(1), rs.getLong(2)))
                .list();

        List<ActorCount> topActors = jdbc.sql("""
                        SELECT p.slug, p.name_ko, count(DISTINCT s.drama_id) AS n
                          FROM user_drama_state s
                          JOIN credit c ON c.drama_id = s.drama_id AND c.credit_type = 'ACTOR'
                          JOIN person p ON p.id = c.person_id
                         WHERE s.user_id = :u AND s.status = 'WATCHED' AND p.status = 'PUBLISHED'
                         GROUP BY p.id ORDER BY n DESC, p.name_ko
                         LIMIT 10
                        """)
                .param("u", userId)
                .query((rs, i) -> new ActorCount(rs.getString(1), rs.getString(2), rs.getLong(3)))
                .list();

        long total = byStatus.values().stream().mapToLong(Long::longValue).sum();
        return new Timeline(total, byStatus, byYear, byBroadcaster, byGenre, topActors);
    }
}
