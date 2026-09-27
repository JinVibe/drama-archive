package com.dramamemory.domainapi.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.dramamemory.domainapi.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@TestPropertySource(properties = "dramamemory.admin.token=test-admin-token")
class AdminReviewApiTest {

    private static final String TOKEN = "test-admin-token";

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;

    private long stagingId;

    @BeforeEach
    void seed() {
        // canonical 김원석 (director) already exists; incoming 김원석 (writer) went to REVIEW.
        jdbc.sql("""
                INSERT INTO person (id, slug, name_ko, name_normalized) VALUES (901, 'kim-won-seok', '김원석', '김원석')
                ON CONFLICT (id) DO NOTHING
                """).update();
        jdbc.sql("""
                INSERT INTO drama (id, slug, title_ko, title_normalized, start_date) VALUES (901, 'rv-signal', '시그널', '시그널', '1993-01-01')
                ON CONFLICT (id) DO NOTHING
                """).update();
        jdbc.sql("INSERT INTO credit (drama_id, person_id, credit_type) VALUES (901, 901, 'DIRECTOR') ON CONFLICT DO NOTHING").update();
        jdbc.sql("INSERT INTO source (id, code, source_type, trust_level) VALUES (901, 'rv-test', 'MANUAL', 50) ON CONFLICT (id) DO NOTHING").update();
        jdbc.sql("DELETE FROM staging_record WHERE source_record_id IN (SELECT id FROM source_record WHERE source_id = 901)").update();
        jdbc.sql("DELETE FROM source_record WHERE source_id = 901").update();
        long srId = jdbc.sql("""
                        INSERT INTO source_record (source_id, external_id, entity_type, source_url, fetched_at)
                        VALUES (901, 'rv-dots', 'DRAMA', 'https://x/dots', now()) RETURNING id
                        """).query(Long.class).single();
        stagingId = jdbc.sql("""
                        INSERT INTO staging_record (source_record_id, entity_type, parser_version, payload, status, resolution)
                        VALUES (:sr, 'DRAMA', 'test/1', :payload::jsonb, 'REVIEW', :resolution::jsonb) RETURNING id
                        """)
                .param("sr", srId)
                .param("payload", """
                        {"external_id":"rv-dots","title_ko":"태양의 후예","title_normalized":"태양의후예","broadcaster_code":"kbs",
                         "credits":[{"person":{"external_id":"kim-won-seok-writer","name_ko":"김원석","name_normalized":"김원석","birth_date":null},
                                     "credit_type":"WRITER","character_name":null}],
                         "osts":[]}
                        """)
                .param("resolution", """
                        {"drama":{"decision":"CREATE_NEW","canonical_id":null,"method":"NONE","confidence":0.0,"signals":{}},
                         "persons":{"kim-won-seok-writer":{"decision":"REVIEW","canonical_id":901,"method":"SCORED","confidence":0.85,
                                                           "signals":{"name":1.0,"birth_date":null}}},
                         "songs":{},"artists":{},"needs_review":true}
                        """)
                .query(Long.class).single();
    }

    @Test
    void requires_token() throws Exception {
        mvc.perform(get("/api/v1/admin/review")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/admin/review").header("X-Admin-Token", "wrong")).andExpect(status().isUnauthorized());
    }

    @Test
    void lists_review_entities_with_candidate_context_and_applies_decision() throws Exception {
        mvc.perform(get("/api/v1/admin/review").header("X-Admin-Token", TOKEN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.stagingId == " + stagingId + ")].dramaTitle").value("태양의 후예"))
                .andExpect(jsonPath("$[?(@.stagingId == " + stagingId + ")].entities[0].kind").value("persons"))
                .andExpect(jsonPath("$[?(@.stagingId == " + stagingId + ")].entities[0].key").value("kim-won-seok-writer"))
                .andExpect(jsonPath("$[?(@.stagingId == " + stagingId + ")].entities[0].incomingContext").value("WRITER"))
                .andExpect(jsonPath("$[?(@.stagingId == " + stagingId + ")].entities[0].candidate.name").value("김원석"))
                .andExpect(jsonPath("$[?(@.stagingId == " + stagingId + ")].entities[0].candidate.works[0]").value("시그널 (DIRECTOR)"));

        mvc.perform(post("/api/v1/admin/review/" + stagingId + "/decide").header("X-Admin-Token", TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decisions\":[{\"kind\":\"persons\",\"key\":\"kim-won-seok-writer\",\"decision\":\"CREATE_NEW\"}]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("RESOLVED"))
                .andExpect(jsonPath("$.remainingReviews").value(0));

        String resolution = jdbc.sql("SELECT resolution::text FROM staging_record WHERE id = :id").param("id", stagingId)
                .query(String.class).single();
        assertThat(resolution).contains("\"method\": \"MANUAL\"").contains("\"reviewed_by\": \"admin\"")
                .contains("\"needs_review\": false");
        assertThat(jdbc.sql("SELECT status FROM staging_record WHERE id = :id").param("id", stagingId)
                .query(String.class).single()).isEqualTo("RESOLVED");
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'ADMIN_REVIEW_DECIDED'")
                .query(Long.class).single()).isGreaterThanOrEqualTo(1);

        // already decided -> 409, and it is no longer listed
        mvc.perform(post("/api/v1/admin/review/" + stagingId + "/decide").header("X-Admin-Token", TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decisions\":[{\"kind\":\"persons\",\"key\":\"kim-won-seok-writer\",\"decision\":\"CREATE_NEW\"}]}"))
                .andExpect(status().isConflict());
        mvc.perform(get("/api/v1/admin/review").header("X-Admin-Token", TOKEN))
                .andExpect(jsonPath("$[?(@.stagingId == " + stagingId + ")]", hasSize(0)));
    }

    @Test
    void merge_requires_canonical_id_and_unknown_key_is_404() throws Exception {
        mvc.perform(post("/api/v1/admin/review/" + stagingId + "/decide").header("X-Admin-Token", TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decisions\":[{\"kind\":\"persons\",\"key\":\"kim-won-seok-writer\",\"decision\":\"AUTO_MERGE\"}]}"))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/v1/admin/review/" + stagingId + "/decide").header("X-Admin-Token", TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decisions\":[{\"kind\":\"persons\",\"key\":\"nobody\",\"decision\":\"CREATE_NEW\"}]}"))
                .andExpect(status().isNotFound());
    }
}
