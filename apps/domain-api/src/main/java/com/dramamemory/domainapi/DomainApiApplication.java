package com.dramamemory.domainapi;

import com.dramamemory.domainapi.user.SessionProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(SessionProperties.class)
public class DomainApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(DomainApiApplication.class, args);
    }
}
