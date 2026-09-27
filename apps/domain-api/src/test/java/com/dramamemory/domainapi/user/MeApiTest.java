package com.dramamemory.domainapi.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.dramamemory.domainapi.TestcontainersConfiguration;
import jakarta.servlet.http.Cookie;
import java.util.UUID;
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
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
class MeApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;
    @Autowired SessionCookieCodec codec;

    @BeforeEach
    void seedDramas() {
        jdbc.sql("DELETE FROM outbox_event").update();
        jdbc.sql("""
                INSERT INTO drama (id, slug, title_ko, title_normalized, start_date)
                -- years outside anything CatalogApiTest asserts on (the container is shared)
                VALUES (101, 'me-a', 'A', 'a', '1999-01-01'), (102, 'me-b', 'B', 'b', '2000-01-01'),
                       (103, 'me-hidden', 'H', 'h', '2001-01-01')
                ON CONFLICT (id) DO NOTHING
                """).update();
        jdbc.sql("UPDATE drama SET status = 'HIDDEN' WHERE id = 103").update();
    }

    private static Cookie sessionCookie(MvcResult result) {
        jakarta.servlet.http.Cookie c = result.getResponse().getCookie("dm_uid");
        assertThat(c).as("session cookie").isNotNull();
        return c;
    }

    @Test
    void reads_without_a_session_are_empty_and_create_nothing() throws Exception {
        long before = jdbc.sql("SELECT count(*) FROM app_user").query(Long.class).single();
        mvc.perform(get("/api/v1/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.anonymous").value(true))
                .andExpect(jsonPath("$.userId").doesNotExist())
                .andExpect(cookie().doesNotExist("dm_uid"));
        mvc.perform(get("/api/v1/me/dramas"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items", hasSize(0)));
        assertThat(jdbc.sql("SELECT count(*) FROM app_user").query(Long.class).single()).isEqualTo(before);
    }

    @Test
    void first_write_creates_anonymous_user_and_sets_signed_httponly_cookie() throws Exception {
        MvcResult r = mvc.perform(put("/api/v1/me/dramas/101/status")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"WATCHED\",\"rating\":4.5,\"firstWatchedYear\":2016}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.drama.slug").value("me-a"))
                .andExpect(jsonPath("$.status").value("WATCHED"))
                .andExpect(jsonPath("$.rating").value(4.5))
                .andExpect(cookie().exists("dm_uid"))
                .andExpect(cookie().httpOnly("dm_uid", true))
                .andExpect(cookie().path("dm_uid", "/"))
                .andReturn();
        Cookie c = sessionCookie(r);
        UUID userId = codec.decode(c.getValue()).orElseThrow();
        assertThat(jdbc.sql("SELECT anonymous FROM app_user WHERE id = :id").param("id", userId)
                .query(Boolean.class).single()).isTrue();

        // Same cookie -> same user; upsert changes status, no second user.
        mvc.perform(put("/api/v1/me/dramas/101/status").cookie(c)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"WATCHING\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("WATCHING"))
                .andExpect(jsonPath("$.rating").doesNotExist())
                .andExpect(cookie().doesNotExist("dm_uid"));
        mvc.perform(put("/api/v1/me/dramas/102/status").cookie(c)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"WANT_TO_WATCH\"}"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/v1/me").cookie(c))
                .andExpect(jsonPath("$.userId").value(userId.toString()))
                .andExpect(jsonPath("$.anonymous").value(true));
        mvc.perform(get("/api/v1/me/dramas/101").cookie(c))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("WATCHING"));
        mvc.perform(get("/api/v1/me/dramas/103").cookie(c)).andExpect(status().isNotFound());
        mvc.perform(get("/api/v1/me/dramas/101")).andExpect(status().isNotFound());
        mvc.perform(get("/api/v1/me/dramas").cookie(c))
                .andExpect(jsonPath("$.items", hasSize(2)))
                .andExpect(jsonPath("$.items[0].drama.id").value(102))
                .andExpect(jsonPath("$.items[1].drama.id").value(101));

        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'USER_DRAMA_STATE_UPDATED'")
                .query(Long.class).single()).isEqualTo(3);
    }

    @Test
    void delete_removes_state_and_emits_event() throws Exception {
        Cookie c = sessionCookie(mvc.perform(put("/api/v1/me/dramas/101/status")
                .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WATCHED\"}")).andReturn());
        mvc.perform(delete("/api/v1/me/dramas/101/status").cookie(c)).andExpect(status().isNoContent());
        mvc.perform(delete("/api/v1/me/dramas/101/status").cookie(c)).andExpect(status().isNotFound());
        mvc.perform(get("/api/v1/me/dramas").cookie(c)).andExpect(jsonPath("$.items", hasSize(0)));
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'USER_DRAMA_STATE_REMOVED'")
                .query(Long.class).single()).isEqualTo(1);
    }

    @Test
    void invalid_input_is_rejected_before_any_user_is_created() throws Exception {
        long before = jdbc.sql("SELECT count(*) FROM app_user").query(Long.class).single();
        mvc.perform(put("/api/v1/me/dramas/101/status")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"LOVED\"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(put("/api/v1/me/dramas/101/status")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WATCHED\",\"rating\":9}"))
                .andExpect(status().isBadRequest());
        mvc.perform(put("/api/v1/me/dramas/103/status")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WATCHED\"}"))
                .andExpect(status().isNotFound());
        mvc.perform(put("/api/v1/me/dramas/999999/status")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WATCHED\"}"))
                .andExpect(status().isNotFound());
        assertThat(jdbc.sql("SELECT count(*) FROM app_user").query(Long.class).single()).isEqualTo(before);
    }

    @Test
    void forged_cookie_is_ignored_and_a_fresh_session_is_issued_on_write() throws Exception {
        Cookie forged = new Cookie("dm_uid", UUID.randomUUID() + ".bm90LWEtcmVhbC1zaWduYXR1cmU");
        mvc.perform(get("/api/v1/me").cookie(forged))
                .andExpect(jsonPath("$.userId").doesNotExist());
        MvcResult r = mvc.perform(put("/api/v1/me/dramas/101/status").cookie(forged)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"WATCHED\"}"))
                .andExpect(status().isOk())
                .andExpect(cookie().exists("dm_uid"))
                .andReturn();
        assertThat(sessionCookie(r).getValue()).isNotEqualTo(forged.getValue());
    }
}
