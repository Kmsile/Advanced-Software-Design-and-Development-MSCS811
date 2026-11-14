import java.io.IOException;
import java.util.Objects;
public final class HybridTextExtractor implements TextExtractionStrategy {
    public enum OcrFailurePolicy { PROPAGATE, RETURN_HTML }

    private final TextExtractionStrategy html;
    private final TextExtractionStrategy ocr;
    private final OcrFailurePolicy failurePolicy;

    public HybridTextExtractor(TextExtractionStrategy html, TextExtractionStrategy ocr) {
        this(html, ocr, OcrFailurePolicy.PROPAGATE);
    }

    public HybridTextExtractor(TextExtractionStrategy html, TextExtractionStrategy ocr,
                               OcrFailurePolicy failurePolicy) {
        this.html = Objects.requireNonNull(html);
        this.ocr = Objects.requireNonNull(ocr);
        this.failurePolicy = Objects.requireNonNull(failurePolicy);
    }

    @Override
    public String extract(PageInput input) throws IOException {
        String htmlResult = "[HTML]\n" + html.extract(input);
        try {
            return htmlResult + "\n[OCR]\n" + ocr.extract(input);
        } catch (IOException error) {
            if (failurePolicy == OcrFailurePolicy.RETURN_HTML && !Thread.currentThread().isInterrupted()) {
                return htmlResult;
            }
            throw error;
        }
    }
}
