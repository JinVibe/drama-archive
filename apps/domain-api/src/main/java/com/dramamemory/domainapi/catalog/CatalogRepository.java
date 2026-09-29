package com.dramamemory.domainapi.catalog;

import com.dramamemory.domainapi.catalog.CatalogDtos.Artist;
import com.dramamemory.domainapi.catalog.CatalogDtos.Broadcaster;
import com.dramamemory.domainapi.catalog.CatalogDtos.Credit;
import com.dramamemory.domainapi.catalog.CatalogDtos.DramaDetail;
import com.dramamemory.domainapi.catalog.CatalogDtos.DramaSummary;
import com.dramamemory.domainapi.catalog.CatalogDtos.FilmographyEntry;
import com.dramamemory.domainapi.catalog.CatalogDtos.Ost;
import com.dramamemory.domainapi.catalog.CatalogDtos.Page;
import com.dramamemory.domainapi.catalog.CatalogDtos.PersonDetail;
import com.dramamemory.domainapi.catalog.CatalogDtos.SynopsisSource;
import com.dramamemory.domainapi.catalog.CatalogDtos.WatchLink;
import com.dramamemory.domainapi.catalog.CatalogDtos.YearCount;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * Read-only access to the canonical catalog. Only PUBLISHED rows are visible; MERGED rows
 * resolve to their target so old URLs keep working.
 */
@Repository
public class CatalogRepository {

    private final JdbcClient jdbc;

    public CatalogRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    // ------------------------------------------------------------------ broadcasters

    /** Channels that currently have at least one published drama (the taxonomy is wider than
     *  the archive's scope, so an empty channel would only be a dead filter). */
    public List<Broadcaster> broadcasters() {
        return jdbc.sql("""
                        SELECT b.code, b.name_ko, b.name_en, b.official_url
                          FROM broadcaster b
                         WHERE EXISTS (SELECT 1 FROM drama d
                                        WHERE d.broadcaster_id = b.id AND d.status = 'PUBLISHED')
                         ORDER BY b.id
                        """)
                .query((rs, i) -> broadcaster(rs))
                .list();
    }

    private static Broadcaster broadcaster(ResultSet rs) throws SQLException {
        String code = rs.getString("code");
        return code == null
                ? null
                : new Broadcaster(code, rs.getString("name_ko"), rs.getString("name_en"), rs.getString("official_url"));
    }

    // ------------------------------------------------------------------ year archive

    public List<YearCount> years() {
        return jdbc.sql("""
                        SELECT EXTRACT(YEAR FROM start_date)::int AS year, count(*) AS n
                          FROM drama
                         WHERE status = 'PUBLISHED' AND start_date IS NOT NULL
                         GROUP BY 1 ORDER BY 1 DESC
                        """)
                .query((rs, i) -> new YearCount(rs.getInt("year"), rs.getLong("n")))
                .list();
    }

    private static final String SUMMARY_SELECT = """
            SELECT d.id, d.slug, d.title_ko, d.title_en, d.start_date, d.end_date, d.episode_count,
                   d.popularity_score,
                   b.code, b.name_ko, b.name_en, b.official_url,
                   (SELECT string_agg(g.code, ',' ORDER BY g.code)
                      FROM drama_genre dg JOIN genre g ON g.id = dg.genre_id
                     WHERE dg.drama_id = d.id) AS genres
              FROM drama d
              LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
            """;

    public Page<DramaSummary> byYear(int year, Optional<String> broadcasterCode, int page, int size) {
        String where = """
                WHERE d.status = 'PUBLISHED'
                  AND d.start_date >= make_date(CAST(:year AS int), 1, 1)
                  AND d.start_date <  make_date(CAST(:year AS int) + 1, 1, 1)
                  AND (CAST(:bc AS text) IS NULL OR b.code = CAST(:bc AS text))
                """;
        long total = jdbc.sql("SELECT count(*) FROM drama d LEFT JOIN broadcaster b ON b.id = d.broadcaster_id " + where)
                .param("year", year)
                .param("bc", broadcasterCode.orElse(null))
                .query(Long.class)
                .single();
        List<DramaSummary> items = jdbc.sql(SUMMARY_SELECT + where
                        + " ORDER BY d.start_date, d.id LIMIT :limit OFFSET :offset")
                .param("year", year)
                .param("bc", broadcasterCode.orElse(null))
                .param("limit", size)
                .param("offset", (long) page * size)
                .query((rs, i) -> summary(rs))
                .list();
        return new Page<>(items, page, size, total);
    }

    /** Most-read dramas across the catalog (Korean Wikipedia page views, trailing year). */
    public List<DramaSummary> popular(int limit) {
        return jdbc.sql(SUMMARY_SELECT + """
                        WHERE d.status = 'PUBLISHED' AND d.popularity_score > 0
                        ORDER BY d.popularity_score DESC, d.id
                        LIMIT :limit
                        """)
                .param("limit", limit)
                .query((rs, i) -> summary(rs))
                .list();
    }

    private static DramaSummary summary(ResultSet rs) throws SQLException {
        return new DramaSummary(
                rs.getLong("id"),
                rs.getString("slug"),
                rs.getString("title_ko"),
                rs.getString("title_en"),
                broadcaster(rs),
                rs.getObject("start_date", java.time.LocalDate.class),
                rs.getObject("end_date", java.time.LocalDate.class),
                rs.getObject("episode_count", Integer.class),
                csv(rs.getString("genres")),
                popularity(rs));
    }

    /** NUMERIC(14,2) -> Double; the JDBC driver refuses getObject(..., Double.class) on numeric. */
    private static Double popularity(ResultSet rs) throws SQLException {
        java.math.BigDecimal v = rs.getBigDecimal("popularity_score");
        return v == null ? null : v.doubleValue();
    }

    // ------------------------------------------------------------------ drama detail

    /** Same rules as {@link #dramaBySlug}: MERGED redirects, only PUBLISHED is visible. */
    public DramaDetail dramaById(long id) {
        String slug = jdbc.sql("SELECT slug FROM drama WHERE id = :id")
                .param("id", id)
                .query(String.class)
                .optional()
                .orElseThrow(() -> new NotFoundException("drama", Long.toString(id)));
        return dramaBySlug(slug);
    }

    public PersonDetail personById(long id) {
        String slug = jdbc.sql("SELECT slug FROM person WHERE id = :id")
                .param("id", id)
                .query(String.class)
                .optional()
                .orElseThrow(() -> new NotFoundException("person", Long.toString(id)));
        return personBySlug(slug);
    }

    public DramaDetail dramaBySlug(String slug) {
        record Head(long id, String status, Long mergedIntoId) {}
        Head head = jdbc.sql("SELECT id, status, merged_into_id FROM drama WHERE slug = :slug")
                .param("slug", slug)
                .query((rs, i) -> new Head(rs.getLong("id"), rs.getString("status"), rs.getObject("merged_into_id", Long.class)))
                .optional()
                .orElseThrow(() -> new NotFoundException("drama", slug));

        if ("MERGED".equals(head.status()) && head.mergedIntoId() != null) {
            String target = jdbc.sql("SELECT slug FROM drama WHERE id = :id")
                    .param("id", head.mergedIntoId())
                    .query(String.class)
                    .single();
            throw new MergedException(target);
        }
        if (!"PUBLISHED".equals(head.status())) {
            throw new NotFoundException("drama", slug);
        }
        long id = head.id();

        return jdbc.sql("""
                        SELECT d.id, d.slug, d.title_ko, d.title_en, d.start_date, d.end_date, d.episode_count,
                               d.runtime_minutes, d.synopsis, d.official_page_url, d.canonical_version,
                               d.synopsis_source, d.synopsis_source_url, d.synopsis_license,
                               b.code, b.name_ko, b.name_en, b.official_url,
                               (SELECT string_agg(g.code, ',' ORDER BY g.code)
                                  FROM drama_genre dg JOIN genre g ON g.id = dg.genre_id
                                 WHERE dg.drama_id = d.id) AS genres,
                               (SELECT string_agg(a.alias, '\u001f' ORDER BY a.alias)
                                  FROM drama_alias a WHERE a.drama_id = d.id) AS aliases
                          FROM drama d LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
                         WHERE d.id = :id
                        """)
                .param("id", id)
                .query((rs, i) -> new DramaDetail(
                        rs.getLong("id"),
                        rs.getString("slug"),
                        rs.getString("title_ko"),
                        rs.getString("title_en"),
                        split(rs.getString("aliases"), "\u001f"),
                        broadcaster(rs),
                        rs.getObject("start_date", java.time.LocalDate.class),
                        rs.getObject("end_date", java.time.LocalDate.class),
                        rs.getObject("episode_count", Integer.class),
                        rs.getObject("runtime_minutes", Integer.class),
                        rs.getString("synopsis"),
                        synopsisSource(rs),
                        rs.getString("official_page_url"),
                        csv(rs.getString("genres")),
                        credits(id),
                        osts(id),
                        links(id),
                        rs.getLong("canonical_version")))
                .single();
    }

    private static SynopsisSource synopsisSource(ResultSet rs) throws SQLException {
        String code = rs.getString("synopsis_source");
        if (code == null || rs.getString("synopsis") == null || code.endsWith(":none")) {
            return null;
        }
        return new SynopsisSource(code, rs.getString("synopsis_source_url"), rs.getString("synopsis_license"));
    }

    private List<Credit> credits(long dramaId) {
        return jdbc.sql("""
                        SELECT p.id, p.slug, p.name_ko, p.name_en, c.credit_type, c.character_name,
                               c.billing_order, c.is_main_cast
                          FROM credit c JOIN person p ON p.id = c.person_id
                         WHERE c.drama_id = :id AND p.status = 'PUBLISHED'
                         ORDER BY CASE c.credit_type WHEN 'ACTOR' THEN 0 WHEN 'DIRECTOR' THEN 1
                                                     WHEN 'WRITER' THEN 2 ELSE 3 END,
                                  c.billing_order NULLS LAST, p.name_ko
                        """)
                .param("id", dramaId)
                .query((rs, i) -> new Credit(
                        rs.getLong("id"),
                        rs.getString("slug"),
                        rs.getString("name_ko"),
                        rs.getString("name_en"),
                        rs.getString("credit_type"),
                        rs.getString("character_name"),
                        rs.getObject("billing_order", Integer.class),
                        rs.getBoolean("is_main_cast")))
                .list();
    }

    private List<Ost> osts(long dramaId) {
        Map<Long, Ost> bySong = jdbc.sql("""
                        SELECT s.id AS song_id, s.title, s.release_date, o.part_no, o.track_no,
                               a.id AS artist_id, a.name AS artist_name, sa.role
                          FROM drama_ost o
                          JOIN song s ON s.id = o.song_id
                          LEFT JOIN song_artist sa ON sa.song_id = s.id
                          LEFT JOIN artist a ON a.id = sa.artist_id
                         WHERE o.drama_id = :id
                         ORDER BY o.part_no NULLS LAST, o.track_no NULLS LAST, s.id, sa.sort_order
                        """)
                .param("id", dramaId)
                .query(rs -> {
                    Map<Long, Ost> acc = new LinkedHashMap<>();
                    while (rs.next()) {
                        long songId = rs.getLong("song_id");
                        Ost ost = acc.computeIfAbsent(songId, k -> {
                            try {
                                return new Ost(
                                        songId,
                                        rs.getString("title"),
                                        rs.getObject("release_date", java.time.LocalDate.class),
                                        rs.getObject("part_no", Integer.class),
                                        rs.getObject("track_no", Integer.class),
                                        new ArrayList<>());
                            } catch (SQLException e) {
                                throw new IllegalStateException(e);
                            }
                        });
                        Long artistId = rs.getObject("artist_id", Long.class);
                        if (artistId != null) {
                            ost.artists().add(new Artist(artistId, rs.getString("artist_name"), rs.getString("role")));
                        }
                    }
                    return acc;
                });
        return new ArrayList<>(bySong.values());
    }

    private List<WatchLink> links(long dramaId) {
        return jdbc.sql("""
                        SELECT provider_code, url, link_type, region_code, availability_status, last_verified_at
                          FROM streaming_link
                         WHERE drama_id = :id
                           AND availability_status NOT IN ('NOT_FOUND', 'ACCESS_DENIED')
                           AND (valid_to IS NULL OR valid_to > now())
                         ORDER BY link_type, provider_code
                        """)
                .param("id", dramaId)
                .query((rs, i) -> new WatchLink(
                        rs.getString("provider_code"),
                        rs.getString("url"),
                        rs.getString("link_type"),
                        rs.getString("region_code"),
                        rs.getString("availability_status"),
                        rs.getObject("last_verified_at", OffsetDateTime.class)))
                .list();
    }

    // ------------------------------------------------------------------ person

    public PersonDetail personBySlug(String slug) {
        record Head(long id, String status, Long mergedIntoId) {}
        Head head = jdbc.sql("SELECT id, status, merged_into_id FROM person WHERE slug = :slug")
                .param("slug", slug)
                .query((rs, i) -> new Head(rs.getLong("id"), rs.getString("status"), rs.getObject("merged_into_id", Long.class)))
                .optional()
                .orElseThrow(() -> new NotFoundException("person", slug));
        if ("MERGED".equals(head.status()) && head.mergedIntoId() != null) {
            throw new MergedException(jdbc.sql("SELECT slug FROM person WHERE id = :id")
                    .param("id", head.mergedIntoId()).query(String.class).single());
        }
        if (!"PUBLISHED".equals(head.status())) {
            throw new NotFoundException("person", slug);
        }

        List<FilmographyEntry> filmography = jdbc.sql("""
                        SELECT d.id, d.slug, d.title_ko, b.code, d.start_date,
                               c.credit_type, c.character_name, c.is_main_cast
                          FROM credit c
                          JOIN drama d ON d.id = c.drama_id
                          LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
                         WHERE c.person_id = :id AND d.status = 'PUBLISHED'
                         ORDER BY d.start_date DESC NULLS LAST, d.id DESC
                        """)
                .param("id", head.id())
                .query((rs, i) -> new FilmographyEntry(
                        rs.getLong("id"),
                        rs.getString("slug"),
                        rs.getString("title_ko"),
                        rs.getString("code"),
                        rs.getObject("start_date", java.time.LocalDate.class),
                        rs.getString("credit_type"),
                        rs.getString("character_name"),
                        rs.getBoolean("is_main_cast")))
                .list();

        return jdbc.sql("SELECT id, slug, name_ko, name_en, birth_date FROM person WHERE id = :id")
                .param("id", head.id())
                .query((rs, i) -> new PersonDetail(
                        rs.getLong("id"),
                        rs.getString("slug"),
                        rs.getString("name_ko"),
                        rs.getString("name_en"),
                        rs.getObject("birth_date", java.time.LocalDate.class),
                        filmography))
                .single();
    }

    // ------------------------------------------------------------------ helpers

    private static List<String> csv(String value) {
        return split(value, ",");
    }

    private static List<String> split(String value, String sep) {
        return value == null || value.isEmpty() ? List.of() : Arrays.asList(value.split(sep));
    }
}
