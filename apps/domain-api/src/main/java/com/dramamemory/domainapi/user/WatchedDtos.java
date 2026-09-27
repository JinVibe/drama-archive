package com.dramamemory.domainapi.user;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class WatchedDtos {

    private WatchedDtos() {}

    public record Me(UUID userId, boolean anonymous, String displayName) {}

    public record UpdateState(
            @NotNull @Pattern(regexp = "WATCHED|WATCHING|WANT_TO_WATCH") String status,
            @DecimalMin("0.5") @DecimalMax("5.0") BigDecimal rating,
            @Min(1950) @Max(2100) Integer firstWatchedYear) {}

    public record DramaRef(long id, String slug, String titleKo, String broadcasterCode, LocalDate startDate) {}

    public record DramaState(
            DramaRef drama, String status, BigDecimal rating, Integer firstWatchedYear, OffsetDateTime updatedAt) {}

    public record DramaStates(List<DramaState> items) {}

    public record Note(long dramaId, String body, String visibility, OffsetDateTime updatedAt) {}

    public record Timeline(
            long total,
            Map<String, Long> byStatus,
            List<YearCount> byYear,
            List<BroadcasterCount> byBroadcaster,
            List<CodeCount> byGenre,
            List<ActorCount> topActors) {
        public record YearCount(int year, long count) {}
        public record BroadcasterCount(String code, String nameKo, long count) {}
        public record CodeCount(String code, long count) {}
        public record ActorCount(String slug, String nameKo, long count) {}
    }

    public record UpdateNote(@NotBlank @Size(max = 500) String body) {}
}
