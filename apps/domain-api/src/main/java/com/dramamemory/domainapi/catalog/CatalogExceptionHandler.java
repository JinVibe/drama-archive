package com.dramamemory.domainapi.catalog;

import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestControllerAdvice
public class CatalogExceptionHandler {

    @ExceptionHandler(NotFoundException.class)
    ProblemDetail notFound(NotFoundException e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, e.getMessage());
    }

    /** Merged entities keep their old URL working via a permanent redirect to the surviving slug. */
    @ExceptionHandler(MergedException.class)
    ResponseEntity<Void> merged(MergedException e) {
        URI location = ServletUriComponentsBuilder.fromCurrentRequest()
                .replacePath(null)
                // /dramas/{slug} and /dramas/by-id/{id} both redirect to /dramas/{survivor}
                .path(ServletUriComponentsBuilder.fromCurrentRequestUri().build().getPath()
                        .replaceFirst("(/by-id)?/[^/]+$", "/" + e.targetSlug()))
                .build()
                .toUri();
        return ResponseEntity.status(HttpStatus.MOVED_PERMANENTLY).location(location).build();
    }
}
