package com.dramamemory.domainapi.catalog;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.dramamemory.domainapi.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Runs against a real PostgreSQL with db/migrations applied, so the SQL in
 * CatalogRepository is verified against the actual schema.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
class CatalogApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;

    private static boolean seeded;

    @BeforeAll
    static void resetFlag() {
        seeded = false;
    }

    @org.junit.jupiter.api.BeforeEach
    void seed() {
        if (seeded) return;
        seeded = true;
        // broadcaster/genre rows come from the V5 seed migration.
        jdbc.sql("""
                INSERT INTO drama (id, slug, title_ko, title_en, title_normalized, broadcaster_id,
                                   start_date, end_date, episode_count, runtime_minutes, synopsis)
                VALUES (1, 'goblin', '도깨비', 'Guardian: The Lonely and Great God', '도깨비',
                        (SELECT id FROM broadcaster WHERE code = 'tvn'),
                        '2016-12-02', '2017-01-21', 16, 80, '도깨비와 저승사자'),
                       (2, 'signal', '시그널', 'Signal', '시그널',
                        (SELECT id FROM broadcaster WHERE code = 'tvn'),
                        '2016-01-22', '2016-03-12', 16, NULL, NULL),
                       (3, 'hidden-2016', '숨김', NULL, '숨김',
                        (SELECT id FROM broadcaster WHERE code = 'kbs'),
                        '2016-06-01', NULL, NULL, NULL, NULL),
                       (4, 'goblin-old', '도깨비(구)', NULL, '도깨비구', NULL,
                        '2016-12-02', NULL, NULL, NULL, NULL)
                """).update();
        jdbc.sql("UPDATE drama SET status = 'HIDDEN' WHERE id = 3").update();
        jdbc.sql("UPDATE drama SET status = 'MERGED', merged_into_id = 1 WHERE id = 4").update();
        jdbc.sql("""
                INSERT INTO drama_alias (drama_id, alias, alias_normalized) VALUES
                    (1, 'Goblin', 'goblin'), (1, '쓸쓸하고 찬란하神 도깨비', '쓸쓸하고찬란하도깨비')
                """).update();
        jdbc.sql("""
                INSERT INTO drama_genre (drama_id, genre_id)
                SELECT 1, id FROM genre WHERE code IN ('fantasy', 'romance')
                """).update();
        jdbc.sql("""
                INSERT INTO person (id, slug, name_ko, name_en, name_normalized, birth_date) VALUES
                    (1, 'gong-yoo', '공유', 'Gong Yoo', '공유', '1979-07-10'),
                    (2, 'kim-eun-sook', '김은숙', NULL, '김은숙', NULL),
                    (3, 'lee-je-hoon', '이제훈', NULL, '이제훈', NULL)
                """).update();
        jdbc.sql("""
                INSERT INTO credit (drama_id, person_id, credit_type, character_name, billing_order, is_main_cast) VALUES
                    (1, 1, 'ACTOR', '김신', 1, true),
                    (1, 2, 'WRITER', NULL, NULL, false),
                    (2, 3, 'ACTOR', '박해영', 1, true),
                    (2, 2, 'WRITER', NULL, NULL, false)
                """).update();
        jdbc.sql("""
                INSERT INTO song (id, title, title_normalized, release_date) VALUES
                    (1, 'Stay With Me', 'staywithme', '2016-12-03'),
                    (2, 'Beautiful', 'beautiful', NULL)
                """).update();
        jdbc.sql("""
                INSERT INTO artist (id, name, name_normalized) VALUES
                    (1, '찬열', '찬열'), (2, '펀치', '펀치'), (3, '크러쉬', '크러쉬')
                """).update();
        jdbc.sql("""
                INSERT INTO song_artist (song_id, artist_id, role, sort_order) VALUES
                    (1, 1, 'PERFORMER', 1), (1, 2, 'PERFORMER', 2), (2, 3, 'PERFORMER', 1)
                """).update();
        jdbc.sql("INSERT INTO drama_ost (drama_id, song_id, part_no) VALUES (1, 1, 1), (1, 2, 4)").update();
        jdbc.sql("""
                INSERT INTO streaming_link (drama_id, provider_code, url, link_type, availability_status) VALUES
                    (1, 'tvn', 'https://tvn.example/goblin', 'BROADCASTER_PAGE', 'AVAILABLE'),
                    (1, 'dead', 'https://dead.example/goblin', 'OTT_DETAIL', 'NOT_FOUND')
                """).update();
    }

    @Test
    void broadcasters_come_from_seed_migration() throws Exception {
        mvc.perform(get("/api/v1/broadcasters"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[*].code", hasItems("kbs", "mbc", "sbs", "jtbc", "tvn", "netflix")));
    }

    @Test
    void years_lists_years_with_published_dramas_newest_first() throws Exception {
        mvc.perform(get("/api/v1/years"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.year == 2016)].count").value(2))
                .andExpect(jsonPath("$[?(@.year == 2017)]").doesNotExist());
    }

    @Test
    void year_archive_lists_published_dramas_of_that_year_only() throws Exception {
        mvc.perform(get("/api/v1/years/2016"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.items[0].slug").value("signal"))
                .andExpect(jsonPath("$.items[1].slug").value("goblin"))
                .andExpect(jsonPath("$.items[1].broadcaster.code").value("tvn"))
                .andExpect(jsonPath("$.items[1].genres", containsInAnyOrder("fantasy", "romance")));
        mvc.perform(get("/api/v1/years/2017")).andExpect(jsonPath("$.total").value(0));
    }

    @Test
    void year_archive_filters_by_broadcaster_and_paginates() throws Exception {
        mvc.perform(get("/api/v1/years/2016").param("broadcaster", "TVN").param("size", "1"))
                .andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.items", hasSize(1)))
                .andExpect(jsonPath("$.items[0].slug").value("signal"));
        mvc.perform(get("/api/v1/years/2016").param("broadcaster", "kbs"))
                .andExpect(jsonPath("$.total").value(0));
        mvc.perform(get("/api/v1/years/1800")).andExpect(status().isBadRequest());
    }

    @Test
    void drama_detail_includes_credits_ost_links_aliases() throws Exception {
        mvc.perform(get("/api/v1/dramas/goblin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.titleKo").value("도깨비"))
                .andExpect(jsonPath("$.aliases", containsInAnyOrder("Goblin", "쓸쓸하고 찬란하神 도깨비")))
                .andExpect(jsonPath("$.episodeCount").value(16))
                .andExpect(jsonPath("$.credits", hasSize(2)))
                .andExpect(jsonPath("$.credits[0].slug").value("gong-yoo"))
                .andExpect(jsonPath("$.credits[0].characterName").value("김신"))
                .andExpect(jsonPath("$.credits[1].creditType").value("WRITER"))
                .andExpect(jsonPath("$.osts", hasSize(2)))
                .andExpect(jsonPath("$.osts[0].title").value("Stay With Me"))
                .andExpect(jsonPath("$.osts[0].artists[*].name", containsInAnyOrder("찬열", "펀치")))
                .andExpect(jsonPath("$.links", hasSize(1)))  // dead link filtered out
                .andExpect(jsonPath("$.links[0].providerCode").value("tvn"))
                .andExpect(jsonPath("$.canonicalVersion").value(1));
    }

    @Test
    void hidden_and_unknown_dramas_are_404_problem_details() throws Exception {
        mvc.perform(get("/api/v1/dramas/hidden-2016"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.detail").value("drama not found: hidden-2016"));
        mvc.perform(get("/api/v1/dramas/nope")).andExpect(status().isNotFound());
    }

    @Test
    void merged_drama_redirects_permanently_to_survivor() throws Exception {
        mvc.perform(get("/api/v1/dramas/goblin-old"))
                .andExpect(status().isMovedPermanently())
                .andExpect(header().string("Location", endsWith("/api/v1/dramas/goblin")));
    }

    @Test
    void by_id_lookups_follow_the_slug_rules() throws Exception {
        mvc.perform(get("/api/v1/dramas/by-id/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.slug").value("goblin"));
        mvc.perform(get("/api/v1/dramas/by-id/3")).andExpect(status().isNotFound());   // hidden
        mvc.perform(get("/api/v1/dramas/by-id/4"))                                       // merged
                .andExpect(status().isMovedPermanently())
                .andExpect(header().string("Location", endsWith("/api/v1/dramas/goblin")));
        mvc.perform(get("/api/v1/dramas/by-id/999")).andExpect(status().isNotFound());
        mvc.perform(get("/api/v1/persons/by-id/2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.slug").value("kim-eun-sook"));
        mvc.perform(get("/api/v1/persons/by-id/999")).andExpect(status().isNotFound());
    }

    @Test
    void person_detail_has_filmography_newest_first() throws Exception {
        mvc.perform(get("/api/v1/persons/kim-eun-sook"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nameKo").value("김은숙"))
                .andExpect(jsonPath("$.filmography", hasSize(2)))
                .andExpect(jsonPath("$.filmography[0].slug").value("goblin"))
                .andExpect(jsonPath("$.filmography[0].creditType").value("WRITER"))
                .andExpect(jsonPath("$.filmography[1].slug").value("signal"));
        mvc.perform(get("/api/v1/persons/nobody")).andExpect(status().isNotFound());
    }
}
