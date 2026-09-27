package com.dramamemory.domainapi.user;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * @param cookieName   cookie carrying the signed user id
 * @param cookieSecret HMAC key, >= 32 bytes; rotate to invalidate every session
 * @param cookieSecure Secure flag; false only for plain-http local development
 * @param cookieMaxAge lifetime (ADR-011: one year)
 */
@ConfigurationProperties("dramamemory.session")
public record SessionProperties(String cookieName, String cookieSecret, boolean cookieSecure, Duration cookieMaxAge) {

    public SessionProperties {
        if (cookieName == null || cookieName.isBlank()) cookieName = "dm_uid";
        if (cookieMaxAge == null) cookieMaxAge = Duration.ofDays(365);
    }
}
