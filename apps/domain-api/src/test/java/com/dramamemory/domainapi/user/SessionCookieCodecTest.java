package com.dramamemory.domainapi.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SessionCookieCodecTest {

    private static final String SECRET = "0123456789abcdef0123456789abcdef";
    private final SessionCookieCodec codec = new SessionCookieCodec(
            new SessionProperties("dm_uid", SECRET, false, Duration.ofDays(1)));

    @Test
    void round_trips_a_user_id() {
        UUID id = UUID.randomUUID();
        String value = codec.encode(id);
        assertThat(value).startsWith(id + ".");
        assertThat(codec.decode(value)).contains(id);
    }

    @Test
    void rejects_tampered_or_malformed_values() {
        UUID id = UUID.randomUUID();
        String value = codec.encode(id);
        String otherSig = codec.encode(UUID.randomUUID()).split("\\.")[1];
        assertThat(codec.decode(id + "." + otherSig)).isEmpty();
        assertThat(codec.decode(value + "x")).isEmpty();
        assertThat(codec.decode(id.toString())).isEmpty();
        assertThat(codec.decode("")).isEmpty();
        assertThat(codec.decode(null)).isEmpty();
    }

    @Test
    void different_secret_does_not_verify() {
        UUID id = UUID.randomUUID();
        SessionCookieCodec other = new SessionCookieCodec(
                new SessionProperties("dm_uid", "ffffffffffffffffffffffffffffffff", false, Duration.ofDays(1)));
        assertThat(other.decode(codec.encode(id))).isEmpty();
    }

    @Test
    void short_secret_is_refused() {
        assertThatThrownBy(() -> new SessionCookieCodec(new SessionProperties("dm_uid", "short", false, null)))
                .isInstanceOf(IllegalStateException.class);
    }
}
