package com.dramamemory.domainapi.catalog;

import com.dramamemory.domainapi.catalog.CatalogDtos.Broadcaster;
import com.dramamemory.domainapi.catalog.CatalogDtos.DramaDetail;
import com.dramamemory.domainapi.catalog.CatalogDtos.DramaSummary;
import com.dramamemory.domainapi.catalog.CatalogDtos.Page;
import com.dramamemory.domainapi.catalog.CatalogDtos.PersonDetail;
import com.dramamemory.domainapi.catalog.CatalogDtos.YearCount;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.Optional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Public, unauthenticated catalog reads. No LLM, no AI subsystem on this path.
 * Parameter constraints are enforced by Spring MVC built-in method validation (400 problem detail).
 */
@RestController
@RequestMapping("/api/v1")
public class CatalogController {

    private final CatalogRepository catalog;

    public CatalogController(CatalogRepository catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/broadcasters")
    public List<Broadcaster> broadcasters() {
        return catalog.broadcasters();
    }

    /** Years that have at least one published drama, newest first — drives the home page and sitemap. */
    @GetMapping("/years")
    public List<YearCount> years() {
        return catalog.years();
    }

    @GetMapping("/years/{year}")
    public Page<DramaSummary> year(
            @PathVariable @Min(1950) @Max(2100) int year,
            @RequestParam Optional<String> broadcaster,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int size) {
        return catalog.byYear(year, broadcaster.map(String::toLowerCase), page, size);
    }

    @GetMapping("/dramas/{slug}")
    public DramaDetail drama(@PathVariable String slug) {
        return catalog.dramaBySlug(slug);
    }

    /** Id-based lookup for machine clients (MCP tools carry drama_id, not slugs). */
    @GetMapping("/dramas/by-id/{id}")
    public DramaDetail dramaById(@PathVariable @Min(1) long id) {
        return catalog.dramaById(id);
    }

    @GetMapping("/persons/{slug}")
    public PersonDetail person(@PathVariable String slug) {
        return catalog.personBySlug(slug);
    }

    @GetMapping("/persons/by-id/{id}")
    public PersonDetail personById(@PathVariable @Min(1) long id) {
        return catalog.personById(id);
    }
}
