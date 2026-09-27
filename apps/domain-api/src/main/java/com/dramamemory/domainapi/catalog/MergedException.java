package com.dramamemory.domainapi.catalog;

/** The requested entity was merged into another canonical row; callers should follow {@link #targetSlug()}. */
public class MergedException extends RuntimeException {

    private final String targetSlug;

    public MergedException(String targetSlug) {
        super("merged into " + targetSlug);
        this.targetSlug = targetSlug;
    }

    public String targetSlug() {
        return targetSlug;
    }
}
