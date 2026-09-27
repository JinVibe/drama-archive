package com.dramamemory.domainapi.user;

import com.dramamemory.domainapi.catalog.NotFoundException;
import com.dramamemory.domainapi.user.WatchedDtos.DramaState;
import com.dramamemory.domainapi.user.WatchedDtos.DramaStates;
import com.dramamemory.domainapi.user.WatchedDtos.Me;
import com.dramamemory.domainapi.user.WatchedDtos.Note;
import com.dramamemory.domainapi.user.WatchedDtos.Timeline;
import com.dramamemory.domainapi.user.WatchedDtos.UpdateNote;
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
    private final NoteRepository notes;
    private final TimelineRepository timeline;

    public MeController(SessionService sessions, WatchedRepository watched, NoteRepository notes,
            TimelineRepository timeline) {
        this.sessions = sessions;
        this.watched = watched;
        this.notes = notes;
        this.timeline = timeline;
    }

    /** Aggregates for the timeline page; all zeros without a session. */
    @GetMapping("/timeline")
    public Timeline timeline(HttpServletRequest req, HttpServletResponse res) {
        return sessions.current(req, res)
                .map(u -> timeline.build(u.id()))
                .orElseGet(() -> timeline.build(new java.util.UUID(0L, 0L)));
    }

    // ------------------------------------------------------------------ memory note

    @GetMapping("/dramas/{dramaId}/note")
    public Note note(@PathVariable long dramaId, HttpServletRequest req, HttpServletResponse res) {
        return sessions.current(req, res)
                .flatMap(u -> notes.find(u.id(), dramaId))
                .orElseThrow(() -> new NotFoundException("note", Long.toString(dramaId)));
    }

    @PutMapping("/dramas/{dramaId}/note")
    @Transactional
    public Note putNote(@PathVariable long dramaId, @Valid @RequestBody UpdateNote body,
            HttpServletRequest req, HttpServletResponse res) {
        if (!watched.dramaIsPublished(dramaId)) {
            throw new NotFoundException("drama", Long.toString(dramaId));
        }
        CurrentUser user = sessions.currentOrCreate(req, res);
        return notes.upsert(user.id(), dramaId, body.body().strip());
    }

    @DeleteMapping("/dramas/{dramaId}/note")
    @Transactional
    public ResponseEntity<Void> deleteNote(@PathVariable long dramaId, HttpServletRequest req,
            HttpServletResponse res) {
        boolean removed = sessions.current(req, res).map(u -> notes.delete(u.id(), dramaId)).orElse(false);
        return removed ? ResponseEntity.noContent().build() : ResponseEntity.notFound().build();
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

    /** State for one drama: 404 both when there is no session and when nothing is recorded. */
    @GetMapping("/dramas/{dramaId}")
    public DramaState one(@PathVariable long dramaId, HttpServletRequest req, HttpServletResponse res) {
        return sessions.current(req, res)
                .flatMap(u -> watched.find(u.id(), dramaId))
                .orElseThrow(() -> new NotFoundException("state", Long.toString(dramaId)));
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
