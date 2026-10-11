package com.cloudclub.jenkinsdeploylab;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "app.version=42", "app.git-sha=abcdef1234567890", "app.release=build-42-abcdef123456",
        "app.instance=app1"
})
class DeploymentInfoControllerTests {
    @LocalServerPort
    private int port;

    @Test
    void healthReportsStatusAndBuildMetadata() throws Exception {
        String body = get("/health");
        assertThat(body).contains("\"status\":\"UP\"");
        assertBuildMetadata(body);
    }

    @Test
    void versionReportsBuildMetadataAndInstance() throws Exception {
        assertBuildMetadata(get("/version"));
    }

    private String get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://localhost:" + port + path)).GET().build();
        HttpResponse<String> response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        return response.body();
    }

    private void assertBuildMetadata(String body) {
        assertThat(body).contains("\"version\":\"42\"", "\"gitSha\":\"abcdef1234567890\"",
                "\"release\":\"build-42-abcdef123456\"", "\"instance\":\"app1\"");
    }
}
