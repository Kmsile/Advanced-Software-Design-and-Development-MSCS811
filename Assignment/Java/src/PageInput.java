import java.nio.file.Path;
import java.util.Objects;
public final class PageInput {
    public final Path html;
    public final Path screenshot;
    public PageInput(Path html, Path screenshot) {
        this.html = Objects.requireNonNull(html);
        this.screenshot = Objects.requireNonNull(screenshot);
    }
}
