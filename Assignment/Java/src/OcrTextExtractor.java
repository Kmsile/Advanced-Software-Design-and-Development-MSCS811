import java.io.IOException;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import java.util.Objects;
public final class OcrTextExtractor implements TextExtractionStrategy {
    private final String node;
    private final Path bridge;
    public OcrTextExtractor(String node, Path bridge) {
        this.node = Objects.requireNonNull(node);
        this.bridge = Objects.requireNonNull(bridge);
    }
    public String extract(PageInput input) throws IOException {
        if (!Files.isRegularFile(input.screenshot))
            throw new IOException("Screenshot does not exist: " + input.screenshot);
        Path output = Files.createTempFile("ocr-output-", ".txt");
        Path errors = Files.createTempFile("ocr-errors-", ".txt");
        Process process = null;
        try {
            process = new ProcessBuilder(node, bridge.toAbsolutePath().toString(),
                input.screenshot.toAbsolutePath().toString())
                .redirectOutput(output.toFile()).redirectError(errors.toFile()).start();
            if (!process.waitFor(60, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                throw new IOException("OCR exceeded the 60-second limit");
            }
            if (process.exitValue() != 0)
                throw new IOException("OCR failed: " + new String(Files.readAllBytes(errors), StandardCharsets.UTF_8));
            return new String(Files.readAllBytes(output), StandardCharsets.UTF_8).trim();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("OCR interrupted", e);
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
            Files.deleteIfExists(output);
            Files.deleteIfExists(errors);
        }
    }
}
