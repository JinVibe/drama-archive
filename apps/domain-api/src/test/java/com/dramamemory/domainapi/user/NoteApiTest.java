package com.dramamemory.domainapi.user;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
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
class NoteApiTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;

    @BeforeEach
    void seed() {
        jdbc.sql("""
                INSERT INTO drama (id, slug, title_ko, title_normalized, start_date)
                VALUES (301, 'note-a', 'A', 'a', '1998-01-01') ON CONFLICT (id) DO NOTHING
                """).update();
    }

    @Test
    void note_round_trip_is_private_and_session_scoped() throws Exception {
        Cookie c = mvc.perform(put("/api/v1/me/dramas/301/note")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"body\":\"  고3 수능 끝나고 가족이랑 봤다  \"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.body").value("고3 수능 끝나고 가족이랑 봤다"))
                .andExpect(jsonPath("$.visibility").value("PRIVATE"))
                .andExpect(cookie().exists("dm_uid"))
                .andReturn().getResponse().getCookie("dm_uid");

        mvc.perform(put("/api/v1/me/dramas/301/note").cookie(c)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"body\":\"수정\"}"))
                .andExpect(jsonPath("$.body").value("수정"));
        mvc.perform(get("/api/v1/me/dramas/301/note").cookie(c))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.body").value("수정"));

        // another browser cannot see it
        mvc.perform(get("/api/v1/me/dramas/301/note")).andExpect(status().isNotFound());

        mvc.perform(delete("/api/v1/me/dramas/301/note").cookie(c)).andExpect(status().isNoContent());
        mvc.perform(get("/api/v1/me/dramas/301/note").cookie(c)).andExpect(status().isNotFound());
    }

    @Test
    void validation() throws Exception {
        mvc.perform(put("/api/v1/me/dramas/301/note")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"body\":\"   \"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(put("/api/v1/me/dramas/301/note")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"body\":\"" + "x".repeat(501) + "\"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(put("/api/v1/me/dramas/999999/note")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"body\":\"x\"}"))
                .andExpect(status().isNotFound());
    }
}
