package com.dramamemory.domainapi.admin;

import com.dramamemory.domainapi.admin.AdminDtos.DecideRequest;
import com.dramamemory.domainapi.admin.AdminDtos.DecideResult;
import com.dramamemory.domainapi.admin.AdminDtos.ProblemItem;
import com.dramamemory.domainapi.admin.AdminDtos.ReviewItem;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponseException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Admin review queue (DM-104). Guarded by a shared token until OAuth + RBAC exist
 * (ARCHITECTURE §12 "Admin Auth (stronger policy)"). With an empty token the
 * endpoints are disabled, never open.
 */
@RestController
@RequestMapping("/api/v1/admin")
public class AdminController {

    private final AdminReviewRepository reviews;
    private final String adminToken;

    public AdminController(AdminReviewRepository reviews,
            @Value("${dramamemory.admin.token:}") String adminToken) {
        this.reviews = reviews;
        this.adminToken = adminToken;
    }

    private void authorize(String token) {
        if (adminToken == null || adminToken.isBlank()) {
            throw new ErrorResponseException(HttpStatus.SERVICE_UNAVAILABLE,
                    ProblemDetail.forStatusAndDetail(HttpStatus.SERVICE_UNAVAILABLE, "admin API disabled: no token configured"), null);
        }
        if (token == null || !java.security.MessageDigest.isEqual(token.getBytes(), adminToken.getBytes())) {
            throw new ErrorResponseException(HttpStatus.UNAUTHORIZED,
                    ProblemDetail.forStatusAndDetail(HttpStatus.UNAUTHORIZED, "bad admin token"), null);
        }
    }

    @GetMapping("/review")
    public List<ReviewItem> pending(@RequestHeader(value = "X-Admin-Token", required = false) String token) {
        authorize(token);
        return reviews.pending();
    }

    @GetMapping("/problems")
    public List<ProblemItem> problems(@RequestHeader(value = "X-Admin-Token", required = false) String token) {
        authorize(token);
        return reviews.problems();
    }

    @PostMapping("/review/{stagingId}/decide")
    public DecideResult decide(@PathVariable long stagingId, @Valid @RequestBody DecideRequest body,
            @RequestHeader(value = "X-Admin-Token", required = false) String token) {
        authorize(token);
        return reviews.decide(stagingId, body.decisions(), "admin");
    }

    @ExceptionHandler({IllegalStateException.class, IllegalArgumentException.class})
    ProblemDetail conflict(RuntimeException e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, e.getMessage());
    }
}
