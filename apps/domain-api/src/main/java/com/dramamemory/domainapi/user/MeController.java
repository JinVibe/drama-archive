package com.dramamemory.domainapi.user;

import com.dramamemory.domainapi.catalog.NotFoundException;
import com.dramamemory.domainapi.user.WatchedDtos.DramaState;
import com.dramamemory.domainapi.user.WatchedDtos.DramaStates;
import com.dramamemory.domainapi.user.WatchedDtos.Me;
import com.dramamemory.domainapi.user.WatchedDtos.UpdateState;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The user's own state. Reads work without a session (empty result); the first write
 * creates an anonymous user and sets the session cookie (ADR-011).
 *
 * <p>This path never touches the AI subsystem: a 봤어요 must succeed even when
 * search, Neo4j or the LLM are down (ARCHITECTURE §5.3).
 */
@RestController
@RequestMapping("/api/v1/me")
public class MeController {

    private final SessionService sessions;
    private final WatchedRepository watched;

    public MeController(SessionService sessions, WatchedRepository watched) {
        this.sessions = sessions;
        this.watched = watched;
    }

    @GetMapping
    public Me me(HttpServletRequest req, HttpServletResponse res) {
        return sessions.current(req, res)
                .map(u -> new Me(u.id(), u.anonymous(), u.displayName()))
                .orElse(new Me(null, true, null));
    }

    @GetMapping("/dramas")
    public DramaStates dramas(HttpServletRequest req, HttpServletResponse res) {
        return sessions.current(req, res)
                .map(u -> new DramaStates(watched.list(u.id())))
                .orElse(new DramaStates(List.of()));
    }

    @PutMapping("/dramas/{dramaId}/status")
    @Transactional
    public DramaState put(@PathVariable long dramaId, @Valid @RequestBody UpdateState body,
            HttpServletRequest req, HttpServletResponse res) {
        if (!watched.dramaIsPublished(dramaId)) {
            throw new NotFoundException("drama", Long.toString(dramaId));
        }
        CurrentUser user = sessions.currentOrCreate(req, res);
        return watched.upsert(user.id(), dramaId, body.status(), body.rating(), body.firstWatchedYear());
    }

    @DeleteMapping("/dramas/{dramaId}/status")
    @Transactional
    public ResponseEntity<Void> delete(@PathVariable long dramaId, HttpServletRequest req, HttpServletResponse res) {
        boolean removed = sessions.current(req, res)
                .map(u -> watched.delete(u.id(), dramaId))
                .orElse(false);
        return removed ? ResponseEntity.noContent().build() : ResponseEntity.notFound().build();
    }
}
