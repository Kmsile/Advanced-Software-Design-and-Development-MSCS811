import java.nio.file.*;
public final class Demo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Pass the Node executable path");
        TextExtractionStrategy html = new HtmlTextExtractor();
        TextExtractionStrategy ocr = new OcrTextExtractor(args[0], Paths.get("ocr_bridge.cjs"));
        TextExtractionContext context = new TextExtractionContext(html);
        for (String name : new String[]{"original", "image_text_3"}) {
            PageInput input = new PageInput(Paths.get("fixtures", name + ".html"),
                Paths.get("fixtures", name + ".png"));
            System.out.println("=== " + name + " ===");
            for (TextExtractionStrategy method : new TextExtractionStrategy[]{html, ocr,
                    new HybridTextExtractor(html, ocr)}) {
                context.setStrategy(method);
                String text = context.extractText(input);
                boolean found = text.toLowerCase().replaceAll("\\s+", " ")
                    .contains("enter your email address and password");
                System.out.println(method.getClass().getSimpleName() + " | target recovered: " + found);
                System.out.println(text);
            }
        }
    }
}
