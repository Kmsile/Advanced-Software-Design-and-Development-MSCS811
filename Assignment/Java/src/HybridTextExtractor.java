import java.io.IOException;
import java.util.Objects;
public final class HybridTextExtractor implements TextExtractionStrategy {
    private final TextExtractionStrategy html;
    private final TextExtractionStrategy ocr;
    public HybridTextExtractor(TextExtractionStrategy html, TextExtractionStrategy ocr) {
        this.html = Objects.requireNonNull(html);
        this.ocr = Objects.requireNonNull(ocr);
    }
    public String extract(PageInput input) throws IOException {
        // Preserve provenance instead of silently deleting approximate duplicates.
        return "[HTML]\n" + html.extract(input) + "\n[OCR]\n" + ocr.extract(input);
    }
}
