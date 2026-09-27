package com.dramamemory.domainapi.catalog;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

/** Read models for the public catalog API. Shapes follow docs/PRD.md FR-01 ~ FR-05. */
public final class CatalogDtos {

    private CatalogDtos() {}

    public record Broadcaster(String code, String nameKo, String nameEn, String officialUrl) {}

    public record DramaSummary(
            long id,
            String slug,
            String titleKo,
            String titleEn,
            Broadcaster broadcaster,
            LocalDate startDate,
            LocalDate endDate,
            Integer episodeCount,
            List<String> genres) {}

    public record Page<T>(List<T> items, int page, int size, long total) {}

    public record Credit(
            long personId,
            String slug,
            String nameKo,
            String nameEn,
            String creditType,
            String characterName,
            Integer billingOrder,
            boolean mainCast) {}

    public record Artist(long id, String name, String role) {}

    public record Ost(
            long songId,
            String title,
            LocalDate releaseDate,
            Integer partNo,
            Integer trackNo,
            List<Artist> artists) {}

    public record WatchLink(
            String providerCode,
            String url,
            String linkType,
            String regionCode,
            String availabilityStatus,
            OffsetDateTime lastVerifiedAt) {}

    public record DramaDetail(
            long id,
            String slug,
            String titleKo,
            String titleEn,
            List<String> aliases,
            Broadcaster broadcaster,
            LocalDate startDate,
            LocalDate endDate,
            Integer episodeCount,
            Integer runtimeMinutes,
            String synopsis,
            String officialPageUrl,
            List<String> genres,
            List<Credit> credits,
            List<Ost> osts,
            List<WatchLink> links,
            long canonicalVersion) {}

    public record FilmographyEntry(
            long dramaId,
            String slug,
            String titleKo,
            String broadcasterCode,
            LocalDate startDate,
            String creditType,
            String characterName,
            boolean mainCast) {}

    public record PersonDetail(
            long id,
            String slug,
            String nameKo,
            String nameEn,
            LocalDate birthDate,
            List<FilmographyEntry> filmography) {}
}
