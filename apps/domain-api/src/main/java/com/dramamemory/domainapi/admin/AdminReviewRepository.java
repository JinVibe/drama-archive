package com.dramamemory.domainapi.admin;

import com.dramamemory.domainapi.admin.AdminDtos.Candidate;
import com.dramamemory.domainapi.admin.AdminDtos.DecideResult;
import com.dramamemory.domainapi.admin.AdminDtos.Decision;
import com.dramamemory.domainapi.admin.AdminDtos.Issue;
import com.dramamemory.domainapi.admin.AdminDtos.ProblemItem;
import com.dramamemory.domainapi.admin.AdminDtos.ReviewEntity;
import com.dramamemory.domainapi.admin.AdminDtos.ReviewItem;
import com.dramamemory.domainapi.catalog.NotFoundException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/**
 * Reads the review queue out of staging_record.resolution and writes human decisions
 * back in the same shape the publish DAG expects (method=MANUAL). Publishing itself
 * stays with the DAG, so the canonical write path has exactly one owner.
 */
@Repository
public class AdminReviewRepository {

    private static final List<String> KINDS = List.of("drama", "persons", "songs", "artists");

    private final JdbcClient jdbc;
    private final ObjectMapper json;

    public AdminReviewRepository(JdbcClient jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    // ------------------------------------------------------------------ list

    public List<ReviewItem> pending() {
        return jdbc.sql("""
                        SELECT st.id, s.code, st.payload, st.resolution, st.created_at
                          FROM staging_record st
                          JOIN source_record sr ON sr.id = st.source_record_id
                          JOIN source s ON s.id = sr.source_id
                         WHERE st.status = 'REVIEW'
                         ORDER BY st.created_at, st.id
                        """)
                .query((rs, i) -> toItem(
                        rs.getLong("id"), rs.getString("code"), rs.getString("payload"),
                        rs.getString("resolution"), rs.getObject("created_at", OffsetDateTime.class)))
                .list();
    }

    public List<ProblemItem> problems() {
        return jdbc.sql("""
                        SELECT st.id, st.status, s.code, st.payload, st.issues, st.updated_at
                          FROM staging_record st
                          JOIN source_record sr ON sr.id = st.source_record_id
                          JOIN source s ON s.id = sr.source_id
                         WHERE st.status IN ('REJECTED', 'PARSE_FAILED')
                         ORDER BY st.updated_at DESC
                         LIMIT 200
                        """)
                .query((rs, i) -> new ProblemItem(
                        rs.getLong("id"), rs.getString("status"), rs.getString("code"),
                        titleOf(rs.getString("payload")),
                        rs.getObject("updated_at", OffsetDateTime.class),
                        issues(rs.getString("issues"))))
                .list();
    }

    private ReviewItem toItem(long id, String source, String payloadJson, String resolutionJson,
            OffsetDateTime createdAt) {
        JsonNode payload = read(payloadJson);
        JsonNode resolution = read(resolutionJson);
        List<ReviewEntity> entities = new ArrayList<>();

        JsonNode drama = resolution.path("drama");
        if ("REVIEW".equals(drama.path("decision").asText())) {
            entities.add(entity("drama", "drama", payload.path("title_ko").asText(), null,
                    payload.path("broadcaster_code").asText(null), drama, "DRAMA"));
        }
        for (JsonNode credit : payload.path("credits")) {
            JsonNode person = credit.path("person");
            String key = person.hasNonNull("external_id")
                    ? person.get("external_id").asText()
                    : "name:" + person.path("name_normalized").asText();
            JsonNode match = resolution.path("persons").path(key);
            if ("REVIEW".equals(match.path("decision").asText()) && entities.stream().noneMatch(e -> e.key().equals(key))) {
                String context = credit.path("credit_type").asText() +
                        (credit.hasNonNull("character_name") ? " · " + credit.get("character_name").asText() + " 역" : "");
                entities.add(entity("persons", key, person.path("name_ko").asText(),
                        person.path("birth_date").asText(null), context, match, "PERSON"));
            }
        }
        for (JsonNode song : payload.path("osts")) {
            String key = song.hasNonNull("external_id")
                    ? song.get("external_id").asText()
                    : "title:" + song.path("title_normalized").asText();
            JsonNode match = resolution.path("songs").path(key);
            if ("REVIEW".equals(match.path("decision").asText())) {
                entities.add(entity("songs", key, song.path("title").asText(), null, "OST", match, "SONG"));
            }
            for (JsonNode sa : song.path("artists")) {
                JsonNode artist = sa.path("artist");
                String akey = artist.hasNonNull("external_id")
                        ? artist.get("external_id").asText()
                        : "name:" + artist.path("name_normalized").asText();
                JsonNode amatch = resolution.path("artists").path(akey);
                if ("REVIEW".equals(amatch.path("decision").asText()) && entities.stream().noneMatch(e -> e.key().equals(akey))) {
                    entities.add(entity("artists", akey, artist.path("name").asText(), null, "ARTIST", amatch, "ARTIST"));
                }
            }
        }
        return new ReviewItem(id, source, payload.path("title_ko").asText(),
                payload.path("external_id").asText(), createdAt, entities);
    }

    private ReviewEntity entity(String kind, String key, String name, String birth, String context,
            JsonNode match, String canonicalType) {
        Candidate candidate = match.hasNonNull("canonical_id")
                ? candidate(canonicalType, match.get("canonical_id").asLong())
                : null;
        Map<String, Object> signals = json.convertValue(match.path("signals"), new TypeReference<>() {});
        return new ReviewEntity(kind, key, name, birth, context, match.path("decision").asText(),
                match.hasNonNull("confidence") ? match.get("confidence").asDouble() : null,
                signals == null ? Map.of() : signals, candidate);
    }

    private Candidate candidate(String type, long id) {
        return switch (type) {
            case "PERSON" -> jdbc.sql("""
                            SELECT p.name_ko, p.slug, p.birth_date::text,
                                   (SELECT string_agg(d.title_ko || ' (' || c.credit_type || ')', '\u001f' ORDER BY d.start_date)
                                      FROM credit c JOIN drama d ON d.id = c.drama_id WHERE c.person_id = p.id) AS works
                              FROM person p WHERE p.id = :id
                            """)
                    .param("id", id)
                    .query((rs, i) -> new Candidate(id, rs.getString("name_ko"), rs.getString("slug"),
                            rs.getString("birth_date"), split(rs.getString("works"))))
                    .optional().orElse(null);
            case "DRAMA" -> jdbc.sql("""
                            SELECT d.title_ko, d.slug, d.start_date::text,
                                   (SELECT string_agg(p.name_ko, '\u001f') FROM credit c JOIN person p ON p.id = c.person_id
                                     WHERE c.drama_id = d.id AND c.credit_type = 'ACTOR') AS works
                              FROM drama d WHERE d.id = :id
                            """)
                    .param("id", id)
                    .query((rs, i) -> new Candidate(id, rs.getString("title_ko"), rs.getString("slug"),
                            rs.getString("start_date"), split(rs.getString("works"))))
                    .optional().orElse(null);
            case "SONG" -> jdbc.sql("""
                            SELECT s.title,
                                   (SELECT string_agg(d.title_ko, '\u001f') FROM drama_ost o JOIN drama d ON d.id = o.drama_id
                                     WHERE o.song_id = s.id) AS works
                              FROM song s WHERE s.id = :id
                            """)
                    .param("id", id)
                    .query((rs, i) -> new Candidate(id, rs.getString("title"), null, null, split(rs.getString("works"))))
                    .optional().orElse(null);
            case "ARTIST" -> jdbc.sql("SELECT name FROM artist WHERE id = :id")
                    .param("id", id)
                    .query((rs, i) -> new Candidate(id, rs.getString("name"), null, null, List.of()))
                    .optional().orElse(null);
            default -> null;
        };
    }

    // ------------------------------------------------------------------ decide

    @Transactional
    public DecideResult decide(long stagingId, List<Decision> decisions, String reviewer) {
        record Row(String status, String resolution) {}
        Row row = jdbc.sql("SELECT status, resolution FROM staging_record WHERE id = :id FOR UPDATE")
                .param("id", stagingId)
                .query((rs, i) -> new Row(rs.getString("status"), rs.getString("resolution")))
                .optional()
                .orElseThrow(() -> new NotFoundException("staging record", Long.toString(stagingId)));
        if (!"REVIEW".equals(row.status())) {
            throw new IllegalStateException("staging record " + stagingId + " is " + row.status() + ", not REVIEW");
        }

        ObjectNode resolution = (ObjectNode) read(row.resolution());
        for (Decision d : decisions) {
            JsonNode found = "drama".equals(d.kind())
                    ? resolution.path("drama")
                    : resolution.path(d.kind()).path(d.key());
            if (!found.isObject() || found.isEmpty()) {
                throw new NotFoundException("review entity", d.kind() + "/" + d.key());
            }
            ObjectNode target = (ObjectNode) found;
            if ("AUTO_MERGE".equals(d.decision()) && d.canonicalId() == null) {
                throw new IllegalArgumentException("AUTO_MERGE needs canonicalId for " + d.kind() + "/" + d.key());
            }
            target.put("decision", d.decision());
            if ("AUTO_MERGE".equals(d.decision())) {
                target.put("canonical_id", d.canonicalId());
            } else {
                target.putNull("canonical_id");
            }
            target.put("method", "MANUAL");
            target.put("confidence", 1.0);
            ObjectNode signals = target.has("signals") && target.get("signals").isObject()
                    ? (ObjectNode) target.get("signals") : target.putObject("signals");
            signals.put("reviewed_by", reviewer);
            signals.put("reviewed_at", OffsetDateTime.now().toString());
        }

        int remaining = countReviews(resolution);
        resolution.put("needs_review", remaining > 0);
        String status = remaining > 0 ? "REVIEW" : "RESOLVED";
        jdbc.sql("UPDATE staging_record SET resolution = :r::jsonb, status = :s WHERE id = :id")
                .param("r", resolution.toString()).param("s", status).param("id", stagingId)
                .update();
        jdbc.sql("""
                        INSERT INTO outbox_event (aggregate_type, aggregate_id, event_type, payload)
                        VALUES ('STAGING_RECORD', :id, 'ADMIN_REVIEW_DECIDED',
                                jsonb_build_object('staging_id', CAST(:id AS bigint), 'decisions', CAST(:n AS int),
                                                   'status', CAST(:s AS text)))
                        """)
                .param("id", Long.toString(stagingId)).param("n", decisions.size()).param("s", status)
                .update();
        return new DecideResult(stagingId, status, remaining);
    }

    private static int countReviews(JsonNode resolution) {
        int n = "REVIEW".equals(resolution.path("drama").path("decision").asText()) ? 1 : 0;
        for (String kind : KINDS) {
            if (kind.equals("drama")) continue;
            for (JsonNode m : resolution.path(kind)) {
                if ("REVIEW".equals(m.path("decision").asText())) n++;
            }
        }
        return n;
    }

    // ------------------------------------------------------------------ helpers

    private JsonNode read(String s) {
        try {
            return s == null ? json.createObjectNode() : json.readTree(s);
        } catch (Exception e) {
            throw new IllegalStateException("bad JSON in staging_record", e);
        }
    }

    private String titleOf(String payloadJson) {
        return payloadJson == null ? null : read(payloadJson).path("title_ko").asText(null);
    }

    private List<Issue> issues(String issuesJson) {
        if (issuesJson == null) return List.of();
        List<Issue> out = new ArrayList<>();
        for (JsonNode n : read(issuesJson)) {
            out.add(new Issue(n.path("code").asText(), n.path("severity").asText(), n.path("message").asText()));
        }
        return out;
    }

    private static List<String> split(String v) {
        return v == null || v.isEmpty() ? List.of() : Arrays.asList(v.split("\u001f"));
    }
}
