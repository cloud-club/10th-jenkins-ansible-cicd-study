package com.cloudclub.jenkinsdeploylab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DeploymentInfoController {

    private final String appVersion;
    private final String appInstance;
    private final String gitSha;
    private final String release;

    public DeploymentInfoController(
            @Value("${app.version:local}") String appVersion,
            @Value("${app.instance:local}") String appInstance,
            @Value("${app.git-sha:local}") String gitSha,
            @Value("${app.release:local}") String release) {
        this.appVersion = appVersion;
        this.appInstance = appInstance;
        this.gitSha = gitSha;
        this.release = release;
    }

    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse("UP", appVersion, gitSha, release, appInstance);
    }

    @GetMapping("/version")
    public VersionResponse version() {
        return new VersionResponse(appVersion, gitSha, release, appInstance);
    }

    public record HealthResponse(String status, String version, String gitSha, String release, String instance) {}

    public record VersionResponse(String version, String gitSha, String release, String instance) {
    }
}
