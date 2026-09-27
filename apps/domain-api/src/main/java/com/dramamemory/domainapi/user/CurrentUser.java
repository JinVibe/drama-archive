package com.dramamemory.domainapi.user;

import java.util.UUID;

/** The app_user behind the request's session cookie. */
public record CurrentUser(UUID id, boolean anonymous, String displayName) {}
