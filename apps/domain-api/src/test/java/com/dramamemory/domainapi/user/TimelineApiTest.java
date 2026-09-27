package com.dramamemory.domainapi.user;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.dramamemory.domainapi.TestcontainersConfiguration;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
class TimelineApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;

    @BeforeEach
    void seed() {
        // Two 1990s tvN dramas sharing an actor, one KBS drama; years chosen outside other tests' ranges.
        jdbc.sql("""
                INSERT INTO drama (id, slug, title_ko, title_normalized, broadcaster_id, start_date) VALUES
                    (401, 'tl-a', 'A', 'a', (SELECT id FROM broadcaster WHERE code = 'tvn'), '1991-01-01'),
                    (402, 'tl-b', 'B', 'b', (SELECT id FROM broadcaster WHERE code = 'tvn'), '1991-06-01'),
                    (403, 'tl-c', 'C', 'c', (SELECT id FROM broadcaster WHERE code = 'kbs'), '1992-01-01')
                ON CONFLICT (id) DO NOTHING
                """).update();
        jdbc.sql("""
                INSERT INTO drama_genre (drama_id, genre_id)
                SELECT d, g.id FROM (VALUES (401), (402)) v(d), genre g WHERE g.code = 'romance'
                ON CONFLICT DO NOTHING
                """).update();
        jdbc.sql("""
                INSERT INTO person (id, slug, name_ko, name_normalized) VALUES (401, 'tl-actor', '배우', '배우')
                ON CONFLICT (id) DO NOTHING
                """).update();
        jdbc.sql("""
                INSERT INTO credit (drama_id, person_id, credit_type, character_name) VALUES
                    (401, 401, 'ACTOR', 'x'), (402, 401, 'ACTOR', 'y')
                ON CONFLICT DO NOTHING
                """).update();
    }

    @Test
    void timeline_aggregates_watched_dramas() throws Exception {
        Cookie c = mvc.perform(put("/api/v1/me/dramas/401/status")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WATCHED\"}"))
                .andReturn().getResponse().getCookie("dm_uid");
        mvc.perform(put("/api/v1/me/dramas/402/status").cookie(c)
                .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WATCHED\"}"));
        mvc.perform(put("/api/v1/me/dramas/403/status").cookie(c)
                .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WANT_TO_WATCH\"}"));

        mvc.perform(get("/api/v1/me/timeline").cookie(c))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(3))
                .andExpect(jsonPath("$.byStatus.WATCHED").value(2))
                .andExpect(jsonPath("$.byStatus.WANT_TO_WATCH").value(1))
                .andExpect(jsonPath("$.byYear", hasSize(1)))
                .andExpect(jsonPath("$.byYear[0].year").value(1991))
                .andExpect(jsonPath("$.byYear[0].count").value(2))
                .andExpect(jsonPath("$.byBroadcaster[0].code").value("tvn"))
                .andExpect(jsonPath("$.byBroadcaster[0].count").value(2))
                .andExpect(jsonPath("$.byGenre[0].code").value("romance"))
                .andExpect(jsonPath("$.topActors[0].slug").value("tl-actor"))
                .andExpect(jsonPath("$.topActors[0].count").value(2));
    }

    @Test
    void timeline_without_session_is_all_zeros() throws Exception {
        mvc.perform(get("/api/v1/me/timeline"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(0))
                .andExpect(jsonPath("$.byStatus.WATCHED").value(0))
                .andExpect(jsonPath("$.byYear", hasSize(0)));
    }
}
