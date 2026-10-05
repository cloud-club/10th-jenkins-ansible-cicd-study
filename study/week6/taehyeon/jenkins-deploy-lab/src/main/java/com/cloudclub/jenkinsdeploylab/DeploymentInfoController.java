package com.cloudclub.jenkinsdeploylab;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DeploymentInfoController {

    private final String appVersion;
    private final String appInstance;

    public DeploymentInfoController(
            @Value("${app.version:local}") String appVersion,
            @Value("${app.instance:local}") String appInstance) {
        this.appVersion = appVersion;
        this.appInstance = appInstance;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }

    @GetMapping("/version")
    public VersionResponse version() {
        return new VersionResponse(appVersion, appInstance);
    }

    public record VersionResponse(String version, String instance) {
    }
}
