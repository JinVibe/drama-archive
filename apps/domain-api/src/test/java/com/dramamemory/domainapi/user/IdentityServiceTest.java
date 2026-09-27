package com.dramamemory.domainapi.user;

import static org.assertj.core.api.Assertions.assertThat;

import com.dramamemory.domainapi.TestcontainersConfiguration;
import com.dramamemory.domainapi.user.IdentityService.Consent;
import com.dramamemory.domainapi.user.IdentityService.LinkResult;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
class IdentityServiceTest {

    private static final List<Consent> REQUIRED = List.of(
            new Consent("TERMS", "2026-09", true),
            new Consent("PRIVACY", "2026-09", true),
            new Consent("AGE_14_PLUS", "2026-09", true));

    @Autowired IdentityService identities;
    @Autowired UserRepository users;
    @Autowired WatchedRepository watched;
    @Autowired JdbcClient jdbc;

    @BeforeEach
    void seedDramas() {
        jdbc.sql("""
                INSERT INTO drama (id, slug, title_ko, title_normalized)
                VALUES (201, 'id-a', 'A', 'a'), (202, 'id-b', 'B', 'b'), (203, 'id-c', 'C', 'c')
                ON CONFLICT (id) DO NOTHING
                """).update();
    }

    @Test
    void linking_a_new_identity_upgrades_the_anonymous_user_in_place() {
        UUID anon = users.createAnonymous();
        watched.upsert(anon, 201, "WATCHED", null, null);

        LinkResult r = identities.link(anon, "kakao", "kakao-" + anon, null, "진", REQUIRED);

        assertThat(r.userId()).isEqualTo(anon);
        assertThat(r.merged()).isFalse();
        var me = users.findActive(anon).orElseThrow();
        assertThat(me.anonymous()).isFalse();
        assertThat(me.displayName()).isEqualTo("진");
        assertThat(watched.list(anon)).hasSize(1);
        assertThat(jdbc.sql("SELECT count(*) FROM user_consent WHERE user_id = :u AND granted")
                .param("u", anon).query(Long.class).single()).isEqualTo(3);
        assertThat(jdbc.sql("SELECT upgraded_at IS NOT NULL FROM app_user WHERE id = :u")
                .param("u", anon).query(Boolean.class).single()).isTrue();
    }

    @Test
    void linking_an_identity_owned_by_another_account_merges_into_it_newer_wins() throws Exception {
        UUID existing = users.createAnonymous();
        identities.link(existing, "kakao", "kakao-shared", null, "기존", REQUIRED);
        watched.upsert(existing, 201, "WATCHED", null, null);          // only on existing
        watched.upsert(existing, 202, "WANT_TO_WATCH", null, null);    // older on existing

        UUID anon = users.createAnonymous();
        Thread.sleep(20);
        watched.upsert(anon, 202, "WATCHED", null, 2017);              // newer on anon -> wins
        watched.upsert(anon, 203, "WATCHING", null, null);             // only on anon

        LinkResult r = identities.link(anon, "kakao", "kakao-shared", null, "새", REQUIRED);

        assertThat(r.userId()).isEqualTo(existing);
        assertThat(r.merged()).isTrue();

        // anon is MERGED and its cookie resolves to the survivor
        assertThat(users.findActive(anon).orElseThrow().id()).isEqualTo(existing);
        assertThat(jdbc.sql("SELECT status FROM app_user WHERE id = :u").param("u", anon)
                .query(String.class).single()).isEqualTo("MERGED");

        var states = watched.list(existing);
        assertThat(states).extracting(s -> s.drama().id()).containsExactlyInAnyOrder(201L, 202L, 203L);
        assertThat(states.stream().filter(s -> s.drama().id() == 202).findFirst().orElseThrow().status())
                .isEqualTo("WATCHED");
        assertThat(watched.list(anon)).isEmpty();
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'USER_MERGED'")
                .query(Long.class).single()).isGreaterThanOrEqualTo(1);
    }

    @Test
    void relinking_the_same_identity_is_idempotent() {
        UUID u = users.createAnonymous();
        identities.link(u, "naver", "naver-1", "a@example.com", null, REQUIRED);
        LinkResult again = identities.link(u, "naver", "naver-1", "a@example.com", null, REQUIRED);
        assertThat(again.userId()).isEqualTo(u);
        assertThat(again.merged()).isFalse();
        assertThat(jdbc.sql("SELECT count(*) FROM user_identity WHERE user_id = :u").param("u", u)
                .query(Long.class).single()).isEqualTo(1);
    }
}
