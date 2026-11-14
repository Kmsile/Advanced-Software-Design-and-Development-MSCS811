import java.io.IOException;
public interface TextExtractionStrategy {
    String extract(PageInput input) throws IOException;
}
