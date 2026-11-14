import java.io.IOException;
import java.util.Objects;
public final class TextExtractionContext {
    private TextExtractionStrategy strategy;
    public TextExtractionContext(TextExtractionStrategy strategy) { setStrategy(strategy); }
    public void setStrategy(TextExtractionStrategy strategy) {
        this.strategy = Objects.requireNonNull(strategy);
    }
    public String extractText(PageInput input) throws IOException {
        return strategy.extract(Objects.requireNonNull(input));
    }
}
