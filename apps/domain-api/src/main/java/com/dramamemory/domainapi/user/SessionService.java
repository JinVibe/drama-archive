package com.dramamemory.domainapi.user;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Arrays;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Service;

/**
 * Guest-first sessions (ADR-011 §1). Reads never create a user; the first write does,
 * and sets the signed cookie. A cookie pointing at a MERGED user is transparently
 * re-issued for the surviving account.
 */
@Service
public class SessionService {

    private final SessionCookieCodec codec;
    private final SessionProperties props;
    private final UserRepository users;

    public SessionService(SessionCookieCodec codec, SessionProperties props, UserRepository users) {
        this.codec = codec;
        this.props = props;
        this.users = users;
    }

    /** Existing session, if the cookie is valid and the user is (or merged into) an active user. */
    public Optional<CurrentUser> current(HttpServletRequest request, HttpServletResponse response) {
        Optional<UUID> cookieId = readCookie(request).flatMap(codec::decode);
        if (cookieId.isEmpty()) {
            return Optional.empty();
        }
        Optional<CurrentUser> user = users.findActive(cookieId.get());
        user.ifPresent(u -> {
            users.touch(u.id());
            if (!u.id().equals(cookieId.get())) {
                issue(response, u.id()); // cookie pointed at a merged account
            }
        });
        return user;
    }

    /** Session for a write: reuse the current one or create an anonymous user and set the cookie. */
    public CurrentUser currentOrCreate(HttpServletRequest request, HttpServletResponse response) {
        return current(request, response).orElseGet(() -> {
            UUID id = users.createAnonymous();
            issue(response, id);
            return new CurrentUser(id, true, null);
        });
    }

    public void issue(HttpServletResponse response, UUID userId) {
        ResponseCookie cookie = ResponseCookie.from(props.cookieName(), codec.encode(userId))
                .httpOnly(true)
                .secure(props.cookieSecure())
                .sameSite("Lax")
                .path("/")
                .maxAge(props.cookieMaxAge())
                .build();
        response.addHeader("Set-Cookie", cookie.toString());
    }

    private Optional<String> readCookie(HttpServletRequest request) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) {
            return Optional.empty();
        }
        return Arrays.stream(cookies)
                .filter(c -> props.cookieName().equals(c.getName()))
                .map(Cookie::getValue)
                .findFirst();
    }
}
