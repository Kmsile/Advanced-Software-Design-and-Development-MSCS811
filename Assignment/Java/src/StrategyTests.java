import java.io.IOException;
import java.nio.file.Paths;
public final class StrategyTests {
    private static void check(boolean ok, String name) {
        if (!ok) throw new AssertionError(name);
        System.out.println("PASS " + name);
    }
    public static void main(String[] args) throws Exception {
        PageInput original = new PageInput(Paths.get("fixtures/original.html"), Paths.get("fixtures/original.png"));
        PageInput altered = new PageInput(Paths.get("fixtures/image_text_3.html"), Paths.get("fixtures/image_text_3.png"));
        HtmlTextExtractor html = new HtmlTextExtractor();
        check(html.extract(original).contains("Enter your email address and password"), "HTML retains ordinary text");
        check(!html.extract(altered).contains("Enter your email address and password"), "HTML does not read image pixels");
        TextExtractionContext context = new TextExtractionContext(input -> "first");
        context.setStrategy(input -> "second");
        check(context.extractText(original).equals("second"), "Context delegates to replacement strategy");
        check(new HybridTextExtractor(input -> "A", input -> "B").extract(original)
            .equals("[HTML]\nA\n[OCR]\nB"), "Hybrid preserves both sources");
        try {
            new HybridTextExtractor(input -> "A", input -> { throw new IOException("unavailable"); }).extract(original);
            throw new AssertionError("Failure was hidden");
        } catch (IOException expected) { System.out.println("PASS hybrid propagates extraction failure"); }
        try { context.setStrategy(null); throw new AssertionError("Null accepted"); }
        catch (NullPointerException expected) { System.out.println("PASS null strategy rejected"); }
        OcrTextExtractor ocr = new OcrTextExtractor(args[0], Paths.get("ocr_bridge.cjs"));
        check(ocr.extract(altered).toLowerCase().contains("enter your email address and password"), "Real OCR recovers image-rendered target");
        try { ocr.extract(new PageInput(original.html, Paths.get("fixtures/absent.png"))); throw new AssertionError("Missing image accepted"); }
        catch (IOException expected) { System.out.println("PASS missing screenshot reported"); }
    }
}
