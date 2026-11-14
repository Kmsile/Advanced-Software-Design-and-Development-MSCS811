import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Base64;

/** Evaluates data-only scenarios without executing any model-generated code. */
public final class ScenarioCheck {
    private static final PageInput STUB_INPUT = new PageInput(
        Paths.get("unused.html"), Paths.get("unused.png")
    );

    private static String hybrid(String[] test) {
        IOException htmlError = new IOException("HTML stub failed");
        IOException ocrError = new IOException("OCR stub failed");
        IllegalStateException ocrRuntime = new IllegalStateException("OCR stub runtime error");
        int[] ocrCalls = {0};
        TextExtractionStrategy html = input -> {
            if ("io".equals(test[3])) {
                throw htmlError;
            }
            return test[5];
        };
        TextExtractionStrategy ocr = input -> {
            ocrCalls[0]++;
            switch (test[4]) {
                case "io": throw ocrError;
                case "runtime": throw ocrRuntime;
                case "interrupted":
                    Thread.currentThread().interrupt();
                    throw ocrError;
                default: return test[6];
            }
        };

        HybridTextExtractor extractor;
        if ("default".equals(test[2])) {
            extractor = new HybridTextExtractor(html, ocr);
        } else {
            HybridTextExtractor.OcrFailurePolicy policy = "return_html".equals(test[2])
                ? HybridTextExtractor.OcrFailurePolicy.RETURN_HTML
                : HybridTextExtractor.OcrFailurePolicy.PROPAGATE;
            extractor = new HybridTextExtractor(html, ocr, policy);
        }

        String status = "return";
        String output = "";
        boolean interrupted;
        try {
            output = extractor.extract(STUB_INPUT);
        } catch (IOException error) {
            status = error == htmlError ? "html_io" : error == ocrError ? "ocr_io" : "other_io";
        } catch (IllegalStateException error) {
            status = error == ocrRuntime ? "ocr_runtime" : "other_runtime";
        } finally {
            interrupted = Thread.interrupted();
        }

        if (!test[7].equals(status)) {
            return "Expected status " + test[7] + ", observed " + status;
        }
        if ("return".equals(status) && !test[8].equals(output)) {
            return "Expected text [" + test[8] + "], observed [" + output + "]";
        }
        int expectedCalls = Integer.parseInt(test[9]);
        if (expectedCalls >= 0 && expectedCalls != ocrCalls[0]) {
            return "Expected " + expectedCalls + " OCR calls, observed " + ocrCalls[0];
        }
        if ("interrupted".equals(test[4]) && "ok".equals(test[3]) && !interrupted) {
            return "OCR interrupted but interrupt status was lost";
        }
        return null;
    }

    private static String html(String[] test) throws IOException {
        Path fixture = Files.createTempFile("mscs811-fixture-", ".html");
        try {
            Files.write(fixture, test[2].getBytes(StandardCharsets.UTF_8));
            String output = new HtmlTextExtractor().extract(new PageInput(fixture, STUB_INPUT.screenshot));
            return test[3].equals(output)
                ? null
                : "Expected text [" + test[3] + "], observed [" + output + "]";
        } finally {
            Files.deleteIfExists(fixture);
        }
    }

    public static void main(String[] args) throws IOException {
        Base64.Decoder decoder = Base64.getDecoder();
        Base64.Encoder encoder = Base64.getEncoder();
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        for (String line; (line = input.readLine()) != null; ) {
            String[] test = line.split("\t", -1);
            for (int i = 0; i < test.length; i++) {
                test[i] = new String(decoder.decode(test[i]), StandardCharsets.UTF_8);
            }
            String issue = "hybrid".equals(test[1]) ? hybrid(test) : html(test);
            if (issue == null) {
                System.out.println(test[0] + "\tPASS");
            } else {
                String encoded = encoder.encodeToString(issue.getBytes(StandardCharsets.UTF_8));
                System.out.println(test[0] + "\tFAIL\t" + encoded);
            }
        }
    }
}
