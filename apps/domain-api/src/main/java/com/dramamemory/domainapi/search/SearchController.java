package com.dramamemory.domainapi.search;

import com.dramamemory.domainapi.search.SearchDtos.Hit;
import com.dramamemory.domainapi.search.SearchDtos.Result;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Lexical search. No LLM here; the AI memory search (DM-701+) lives in ai-api. */
@RestController
@RequestMapping("/api/v1/search")
public class SearchController {

    private final SearchRepository repo;

    public SearchController(SearchRepository repo) {
        this.repo = repo;
    }

    @GetMapping
    public Result search(
            @RequestParam @NotBlank @Size(max = 200) String q,
            @RequestParam(defaultValue = "20") @Min(1) @Max(50) int size) {
        long started = System.nanoTime();
        String normalized = SearchRepository.normalize(q);
        List<Hit> hits = repo.search(normalized, size);
        long ms = (System.nanoTime() - started) / 1_000_000;
        String strategy = SearchRepository.strategyOf(hits);
        repo.log(q, normalized, strategy, hits.size(), ms);
        return new Result(q, strategy, hits.size(), hits, ms);
    }
}
