package com.dramamemory.domainapi.user;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.Optional;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

/**
 * Signed session cookie value: {@code <uuid>.<base64url(hmac-sha256(uuid))>}.
 * The cookie identifies the app_user row; it carries no other data. A bad or
 * forged signature is treated as "no session".
 */
@Component
public class SessionCookieCodec {

    private static final String ALGORITHM = "HmacSHA256";
    private final SecretKeySpec key;

    public SessionCookieCodec(SessionProperties props) {
        byte[] secret = props.cookieSecret().getBytes(StandardCharsets.UTF_8);
        if (secret.length < 32) {
            throw new IllegalStateException("dramamemory.session.cookie-secret must be at least 32 bytes");
        }
        this.key = new SecretKeySpec(secret, ALGORITHM);
    }

    public String encode(UUID userId) {
        String id = userId.toString();
        return id + "." + sign(id);
    }

    public Optional<UUID> decode(String value) {
        if (value == null) {
            return Optional.empty();
        }
        int dot = value.indexOf('.');
        if (dot <= 0 || dot == value.length() - 1) {
            return Optional.empty();
        }
        String id = value.substring(0, dot);
        String sig = value.substring(dot + 1);
        if (!MessageDigest.isEqual(
                sig.getBytes(StandardCharsets.UTF_8), sign(id).getBytes(StandardCharsets.UTF_8))) {
            return Optional.empty();
        }
        try {
            return Optional.of(UUID.fromString(id));
        } catch (IllegalArgumentException e) {
            return Optional.empty();
        }
    }

    private String sign(String id) {
        try {
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(mac.doFinal(id.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.GeneralSecurityException e) {
            throw new IllegalStateException(e);
        }
    }
}
