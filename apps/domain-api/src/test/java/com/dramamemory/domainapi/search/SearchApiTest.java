package com.dramamemory.domainapi.search;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.dramamemory.domainapi.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
class SearchApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;

    @BeforeEach
    void seed() {
        jdbc.sql("DELETE FROM search_query_log").update();
        jdbc.sql("""
                INSERT INTO search_document (entity_type, entity_id, title, aliases, body, metadata, content_hash) VALUES
                ('DRAMA', 501, '도깨비', 'Guardian: The Lonely and Great God\nGoblin',
                 '방송사: tvN\n연도: 2016년\n장르: 판타지, 로맨스\n출연: 공유 (김신 역), 김고은 (지은탁 역)\nOST: Stay With Me - 찬열, 펀치',
                 '{"slug":"goblin-s","year":2016,"broadcaster_name":"tvN","genres":["fantasy","romance"],"cast":["공유","김고은"]}', 'h1'),
                ('DRAMA', 502, '시그널', 'Signal',
                 '방송사: tvN\n연도: 2016년\n장르: 스릴러, 범죄\n출연: 이제훈 (박해영 역), 김혜수 (차수현 역)',
                 '{"slug":"signal-s","year":2016,"broadcaster_name":"tvN","genres":["thriller","crime"],"cast":["이제훈","김혜수"]}', 'h2'),
                ('DRAMA', 503, '또 오해영', 'Another Miss Oh',
                 '방송사: tvN\n연도: 2016년\n장르: 로맨스, 코미디\n출연: 에릭 (박도경 역), 서현진 (오해영 역)',
                 '{"slug":"aoh-s","year":2016,"broadcaster_name":"tvN","genres":["romance","comedy"],"cast":["에릭","서현진"]}', 'h3')
                ON CONFLICT (entity_type, entity_id) DO NOTHING
                """).update();
    }

    @Test
    void exact_tokens_hit_via_fts_and_are_logged() throws Exception {
        mvc.perform(get("/api/v1/search").param("q", "공유 판타지"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.hits[0].dramaId").value(501))
                .andExpect(jsonPath("$.hits[0].title").value("도깨비"))
                .andExpect(jsonPath("$.hits[0].metadata.slug").value("goblin-s"))
                .andExpect(jsonPath("$.hits[0].inFts").value(true));
        assertThat(jdbc.sql("SELECT strategy FROM search_query_log WHERE query_raw = '공유 판타지'")
                .query(String.class).single()).isIn("FTS", "FUSED");
    }

    @Test
    void partial_title_hits_via_trigram() throws Exception {
        mvc.perform(get("/api/v1/search").param("q", "도깨"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.hits[0].dramaId").value(501))
                .andExpect(jsonPath("$.hits[0].inTrigram").value(true));
        mvc.perform(get("/api/v1/search").param("q", "goblin"))
                .andExpect(jsonPath("$.hits[0].dramaId").value(501));
    }

    @Test
    void ost_and_character_names_are_searchable_and_multiple_hits_are_ranked() throws Exception {
        mvc.perform(get("/api/v1/search").param("q", "Stay With Me"))
                .andExpect(jsonPath("$.hits[0].dramaId").value(501));
        mvc.perform(get("/api/v1/search").param("q", "박해영"))
                .andExpect(jsonPath("$.hits[0].dramaId").value(502));
        mvc.perform(get("/api/v1/search").param("q", "로맨스"))
                .andExpect(jsonPath("$.hits", hasSize(2)));
    }

    @Test
    void zero_results_are_logged_for_alias_curation() throws Exception {
        mvc.perform(get("/api/v1/search").param("q", "존재하지않는드라마"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(0))
                .andExpect(jsonPath("$.strategy").value("NONE"));
        assertThat(jdbc.sql("SELECT result_count FROM search_query_log WHERE query_raw = '존재하지않는드라마'")
                .query(Integer.class).single()).isZero();
    }

    @Test
    void validation() throws Exception {
        mvc.perform(get("/api/v1/search").param("q", "   ")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/v1/search").param("q", "x").param("size", "500")).andExpect(status().isBadRequest());
    }
}
