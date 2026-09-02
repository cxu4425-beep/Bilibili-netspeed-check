package tw.lagscope.viewer;

/**
 * Deciding whether a newer APK exists, and whether it may be installed.
 *
 * The rules are the desktop updater's rules, for the same reason: this is the
 * one part of the app that downloads a file and then hands it to the package
 * installer. An unverified APK is a far worse thing to run than an unverified
 * anything else, because Android will treat it as an update to this app.
 *
 *   - https only, and from a GitHub release host - checked against a fixed
 *     list, not against whatever the API happened to return.
 *   - the download must match the sha256 the releases API published, or it is
 *     deleted rather than installed.
 *   - no published digest means no automatic install. The releases page is
 *     opened instead, so the person can decide with their eyes open.
 *
 * Everything here is plain Java with no Android imports, which is what makes
 * it testable: the machine this was written on has no phone and no emulator,
 * so logic that cannot run on a bare JVM cannot be checked at all.
 */
public final class Updater {

    /** The asset the phone can install. Anything else in a release is ignored. */
    public static final String APK_ASSET = "LagScope-viewer.apk";

    public static final String RELEASES_API =
            "https://api.github.com/repos/cxu4425-beep/LagScope/releases/latest";
    public static final String RELEASES_PAGE =
            "https://github.com/cxu4425-beep/LagScope/releases/latest";

    private static final String[] ALLOWED_HOSTS = {
        "github.com",
        "www.github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "api.github.com",
    };

    private Updater() { }

    /** What a release offers this app, or an empty result if it offers nothing. */
    public static final class Release {
        public final String version;    // "1.1", with any leading v stripped
        public final String url;        // where the APK is
        public final String sha256;     // lowercase hex, "" when none published
        public final long size;

        Release(String version, String url, String sha256, long size) {
            this.version = version;
            this.url = url;
            this.sha256 = sha256;
            this.size = size;
        }

        public boolean hasApk() {
            return url != null && !url.isEmpty();
        }

        /** Enough to install without asking anyone to trust anything. */
        public boolean installable() {
            return hasApk() && sha256 != null && sha256.length() == 64
                   && hostAllowed(url);
        }
    }

    public static boolean hostAllowed(String url) {
        if (url == null || !url.startsWith("https://")) {
            return false;
        }
        int start = "https://".length();
        int slash = url.indexOf('/', start);
        String authority = slash < 0 ? url.substring(start) : url.substring(start, slash);
        int at = authority.indexOf('@');          // strip any userinfo
        if (at >= 0) { authority = authority.substring(at + 1); }
        int colon = authority.indexOf(':');       // and any port
        if (colon >= 0) { authority = authority.substring(0, colon); }

        String host = authority.toLowerCase();
        for (String allowed : ALLOWED_HOSTS) {
            if (host.equals(allowed)) { return true; }
        }
        return false;
    }

    /**
     * Compare two dotted versions. Absent parts count as zero, so 1.1 and
     * 1.1.0 are the same version rather than one being newer.
     */
    public static boolean isNewer(String candidate, String current) {
        int[] a = parse(candidate);
        int[] b = parse(current);
        if (a.length == 0) {
            return false;               // unreadable is never an upgrade
        }
        int len = Math.max(a.length, b.length);
        for (int i = 0; i < len; i++) {
            int left = i < a.length ? a[i] : 0;
            int right = i < b.length ? b[i] : 0;
            if (left != right) { return left > right; }
        }
        return false;
    }

    static int[] parse(String text) {
        if (text == null) { return new int[0]; }
        String trimmed = text.trim();
        int start = 0;
        while (start < trimmed.length() && !Character.isDigit(trimmed.charAt(start))) {
            start++;
        }
        int end = start;
        while (end < trimmed.length()
               && (Character.isDigit(trimmed.charAt(end)) || trimmed.charAt(end) == '.')) {
            end++;
        }
        if (end <= start) { return new int[0]; }

        String[] parts = trimmed.substring(start, end).split("\\.");
        int count = 0;
        int[] out = new int[parts.length];
        for (String part : parts) {
            if (part.isEmpty()) { continue; }
            try {
                out[count++] = Integer.parseInt(part);
            } catch (NumberFormatException ignored) {
                break;
            }
        }
        int[] trimmedOut = new int[count];
        System.arraycopy(out, 0, trimmedOut, 0, count);
        return trimmedOut;
    }

    /**
     * Read a releases API response without a JSON library.
     *
     * Android ships org.json, but keeping this dependency-free is what lets
     * the parser be tested on a desktop JVM. The shape it reads is small and
     * fixed: a tag name, and inside "assets" the one entry whose name matches
     * the APK, with its download URL, size and digest.
     */
    public static Release parseLatest(String json) {
        if (json == null) { return new Release("", "", "", 0); }

        String version = stripV(stringField(json, "tag_name"));

        // Find the asset block for our APK: from the name backwards to the
        // start of its object, forwards to the end, so the fields read below
        // cannot come from a neighbouring asset.
        String needle = "\"name\":\"" + APK_ASSET + "\"";
        int at = json.indexOf(needle);
        if (at < 0) {
            needle = "\"name\": \"" + APK_ASSET + "\"";
            at = json.indexOf(needle);
        }
        if (at < 0) { return new Release(version, "", "", 0); }

        int open = json.lastIndexOf('{', at);
        int close = json.indexOf('}', at);
        if (open < 0 || close < 0) { return new Release(version, "", "", 0); }
        String block = json.substring(open, close);

        String url = stringField(block, "browser_download_url");
        String digest = stringField(block, "digest");
        String sha = "";
        if (digest.startsWith("sha256:")) {
            sha = digest.substring("sha256:".length()).trim().toLowerCase();
        }
        long size = 0;
        try {
            String raw = numberField(block, "size");
            if (!raw.isEmpty()) { size = Long.parseLong(raw); }
        } catch (NumberFormatException ignored) {
            size = 0;
        }
        return new Release(version, url, sha, size);
    }

    static String stripV(String tag) {
        String value = tag == null ? "" : tag.trim();
        if (value.startsWith("v") || value.startsWith("V")) {
            return value.substring(1);
        }
        return value;
    }

    static String stringField(String json, String key) {
        int at = indexOfKey(json, key);
        if (at < 0) { return ""; }
        int quote = json.indexOf('"', at);
        if (quote < 0) { return ""; }
        int end = quote + 1;
        StringBuilder out = new StringBuilder();
        while (end < json.length()) {
            char c = json.charAt(end);
            if (c == '\\' && end + 1 < json.length()) {
                char next = json.charAt(end + 1);
                if (next == '/' || next == '"' || next == '\\') {
                    out.append(next);
                    end += 2;
                    continue;
                }
            }
            if (c == '"') { break; }
            out.append(c);
            end++;
        }
        return out.toString();
    }

    static String numberField(String json, String key) {
        int at = indexOfKey(json, key);
        if (at < 0) { return ""; }
        int i = at;
        while (i < json.length() && !Character.isDigit(json.charAt(i))) {
            if (json.charAt(i) == ',' || json.charAt(i) == '}') { return ""; }
            i++;
        }
        int start = i;
        while (i < json.length() && Character.isDigit(json.charAt(i))) { i++; }
        return json.substring(start, i);
    }

    /** Position just past `"key":`, tolerating a space after the colon. */
    private static int indexOfKey(String json, String key) {
        String quoted = "\"" + key + "\"";
        int at = json.indexOf(quoted);
        if (at < 0) { return -1; }
        int colon = json.indexOf(':', at + quoted.length());
        return colon < 0 ? -1 : colon + 1;
    }

    /** Lowercase hex of a digest, for comparing against what was published. */
    public static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            out.append(Character.forDigit((b >> 4) & 0xF, 16));
            out.append(Character.forDigit(b & 0xF, 16));
        }
        return out.toString();
    }
}
