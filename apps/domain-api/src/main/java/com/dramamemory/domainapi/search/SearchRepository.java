package com.dramamemory.domainapi.search;

import com.dramamemory.domainapi.search.SearchDtos.Hit;
import java.util.Arrays;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * Lexical search v1 (DM-501): full-text (exact tokens, weighted title/alias/body) and
 * trigram (partial / typo-tolerant title & alias) candidates fused with RRF
 * (README principle 6) — never by adding raw scores.
 */
@Repository
public class SearchRepository {

    /** Standard RRF constant. */
    private static final int RRF_K = 60;
    private static final int CANDIDATES = 50;

    private static final String SQL = """
            WITH q AS (
                SELECT CAST(:q AS text) AS raw, websearch_to_tsquery('simple', CAST(:q AS text)) AS tsq
            ),
            fts AS (
                SELECT sd.id, row_number() OVER (ORDER BY ts_rank_cd(sd.fts, q.tsq) DESC, sd.id) AS rnk
                  FROM search_document sd, q
                 WHERE sd.entity_type = 'DRAMA' AND numnode(q.tsq) > 0 AND sd.fts @@ q.tsq
                 LIMIT %d
            ),
            trgm AS (
                SELECT sd.id,
                       row_number() OVER (ORDER BY GREATEST(word_similarity(q.raw, sd.title),
                                                            word_similarity(q.raw, sd.aliases)) DESC, sd.id) AS rnk
                  FROM search_document sd, q
                 WHERE sd.entity_type = 'DRAMA'
                   AND GREATEST(word_similarity(q.raw, sd.title), word_similarity(q.raw, sd.aliases)) >= 0.35
                 LIMIT %d
            ),
            fused AS (
                SELECT COALESCE(f.id, t.id) AS id,
                       COALESCE(1.0 / (%d + f.rnk), 0) + COALESCE(1.0 / (%d + t.rnk), 0) AS score,
                       f.rnk IS NOT NULL AS in_fts, t.rnk IS NOT NULL AS in_trgm
                  FROM fts f FULL OUTER JOIN trgm t ON f.id = t.id
            )
            SELECT sd.entity_id, sd.title, sd.metadata, fu.score, fu.in_fts, fu.in_trgm
              FROM fused fu JOIN search_document sd ON sd.id = fu.id
             ORDER BY fu.score DESC, sd.entity_id
             LIMIT :limit
            """.formatted(CANDIDATES, CANDIDATES, RRF_K, RRF_K);

    private final JdbcClient jdbc;

    public SearchRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<Hit> search(String query, int limit) {
        return jdbc.sql(SQL)
                .param("q", query)
                .param("limit", limit)
                .query((rs, i) -> new Hit(
                        rs.getLong("entity_id"),
                        rs.getString("title"),
                        rs.getString("metadata"),
                        rs.getDouble("score"),
                        rs.getBoolean("in_fts"),
                        rs.getBoolean("in_trgm")))
                .list();
    }

    public void log(String raw, String normalized, String strategy, int resultCount, long latencyMs) {
        jdbc.sql("""
                        INSERT INTO search_query_log (query_raw, query_normalized, strategy, result_count, latency_ms)
                        VALUES (:raw, :norm, :strategy, :n, :ms)
                        """)
                .param("raw", raw).param("norm", normalized).param("strategy", strategy)
                .param("n", resultCount).param("ms", (int) latencyMs)
                .update();
    }

    /** Which retrieval paths produced the results, for the log and for the evidence UI. */
    static String strategyOf(List<Hit> hits) {
        if (hits.isEmpty()) return "NONE";
        boolean fts = hits.stream().anyMatch(Hit::inFts);
        boolean trgm = hits.stream().anyMatch(Hit::inTrigram);
        return fts && trgm ? "FUSED" : fts ? "FTS" : "TRIGRAM";
    }

    static String normalize(String q) {
        return String.join(" ", Arrays.stream(q.trim().toLowerCase().split("\\s+")).filter(s -> !s.isBlank()).toList());
    }
}
