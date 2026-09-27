package com.dramamemory.domainapi.user;

import com.dramamemory.domainapi.user.WatchedDtos.Note;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** Private memory notes (DATA_MODEL §14: never enters any corpus or telemetry). */
@Repository
public class NoteRepository {

    private final JdbcClient jdbc;

    public NoteRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Note> find(UUID userId, long dramaId) {
        return jdbc.sql("""
                        SELECT drama_id, body, visibility, updated_at
                          FROM memory_note WHERE user_id = :u AND drama_id = :d
                        """)
                .param("u", userId).param("d", dramaId)
                .query((rs, i) -> new Note(
                        rs.getLong("drama_id"),
                        rs.getString("body"),
                        rs.getString("visibility"),
                        rs.getObject("updated_at", OffsetDateTime.class)))
                .optional();
    }

    public Note upsert(UUID userId, long dramaId, String body) {
        jdbc.sql("""
                        INSERT INTO memory_note (user_id, drama_id, body)
                        VALUES (:u, :d, :b)
                        ON CONFLICT (user_id, drama_id) DO UPDATE SET body = EXCLUDED.body
                        """)
                .param("u", userId).param("d", dramaId).param("b", body)
                .update();
        return find(userId, dramaId).orElseThrow();
    }

    public boolean delete(UUID userId, long dramaId) {
        return jdbc.sql("DELETE FROM memory_note WHERE user_id = :u AND drama_id = :d")
                .param("u", userId).param("d", dramaId)
                .update() > 0;
    }
}
