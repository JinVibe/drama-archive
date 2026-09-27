plugins {
    java
    id("org.springframework.boot") version "4.1.1"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.dramamemory"
version = "0.1.0-SNAPSHOT"
description = "DramaMemory Domain API: canonical read API, user state, memory notes"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("org.postgresql:postgresql")

    // Schema is owned by db/migrations and applied before this service starts
    // (compose `migrate`). Flyway here is used by tests only, to build the same
    // schema inside Testcontainers.
    testImplementation("org.springframework.boot:spring-boot-starter-flyway-test")
    testImplementation("org.flywaydb:flyway-database-postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("org.springframework.boot:spring-boot-starter-jdbc-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-postgresql")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test> {
    useJUnitPlatform()
    // Tests apply db/migrations into a Testcontainers PostgreSQL; resolve the path
    // relative to the repo root so it works from Gradle and from an IDE.
    systemProperty("dramamemory.migrations", rootDir.resolve("../../db/migrations").normalize().path)
}
