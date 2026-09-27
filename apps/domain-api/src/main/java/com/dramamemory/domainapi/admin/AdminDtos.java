package com.dramamemory.domainapi.admin;

import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/** Entity-resolution review queue (DM-104). Shapes mirror staging_record.resolution. */
public final class AdminDtos {

    private AdminDtos() {}

    /** What the existing canonical row looks like, so a reviewer can compare. */
    public record Candidate(long canonicalId, String name, String slug, String birthDate, List<String> works) {}

    public record ReviewEntity(
            String kind,            // persons | songs | artists | drama
            String key,             // key inside resolution[kind] (external id or name:/title: key)
            String incomingName,
            String incomingBirthDate,
            String incomingContext, // e.g. "WRITER" or character name
            String decision,
            Double confidence,
            Map<String, Object> signals,
            Candidate candidate) {}

    public record ReviewItem(
            long stagingId,
            String sourceCode,
            String dramaTitle,
            String dramaExternalId,
            OffsetDateTime createdAt,
            List<ReviewEntity> entities) {}

    public record Decision(
            @NotNull @Pattern(regexp = "persons|songs|artists|drama") String kind,
            @NotNull String key,
            @NotNull @Pattern(regexp = "AUTO_MERGE|CREATE_NEW") String decision,
            Long canonicalId) {}

    public record DecideRequest(@NotEmpty List<Decision> decisions) {}

    public record DecideResult(long stagingId, String status, int remainingReviews) {}

    public record Issue(String code, String severity, String message) {}

    public record ProblemItem(long stagingId, String status, String sourceCode, String dramaTitle,
                              OffsetDateTime updatedAt, List<Issue> issues) {}
}
