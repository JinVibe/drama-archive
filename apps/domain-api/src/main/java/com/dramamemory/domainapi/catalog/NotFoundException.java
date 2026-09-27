package com.dramamemory.domainapi.catalog;

public class NotFoundException extends RuntimeException {

    public NotFoundException(String what, String key) {
        super(what + " not found: " + key);
    }
}
