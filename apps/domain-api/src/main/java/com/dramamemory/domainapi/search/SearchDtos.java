package com.dramamemory.domainapi.search;

import com.fasterxml.jackson.annotation.JsonRawValue;
import java.util.List;

public final class SearchDtos {

    private SearchDtos() {}

    /** metadata is the search_document JSON as stored (slug, year, broadcaster, genres, cast...). */
    public record Hit(
            long dramaId,
            String title,
            @JsonRawValue String metadata,
            double score,
            boolean inFts,
            boolean inTrigram) {}

    public record Result(String query, String strategy, int total, List<Hit> hits, long latencyMs) {}
}
