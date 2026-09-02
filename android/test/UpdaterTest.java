import tw.lagscope.viewer.Updater;

/** Runs on a plain JVM: no Android, no device, no emulator. */
public class UpdaterTest {
    private static int failed = 0;

    static void ok(String what, boolean pass) {
        if (pass) { System.out.println("  ok   " + what); }
        else { failed++; System.out.println("  FAIL " + what); }
    }
    static void eq(String what, Object got, Object want) {
        boolean pass = want.equals(got);
        if (pass) { System.out.println("  ok   " + what); }
        else { failed++; System.out.println("  FAIL " + what
                + "\n       got  " + got + "\n       want " + want); }
    }

    static final String JSON =
        "{\"tag_name\":\"v1.2\",\"html_url\":\"https://github.com/x/y/releases/tag/v1.2\","
      + "\"assets\":["
      + "{\"name\":\"LagScope-setup.exe\",\"size\":44,"
      + "\"browser_download_url\":\"https://github.com/x/y/releases/download/v1.2/LagScope-setup.exe\","
      + "\"digest\":\"sha256:" + "b".repeat(64) + "\"},"
      + "{\"name\":\"LagScope-viewer.apk\",\"size\":66345,"
      + "\"browser_download_url\":\"https://github.com/x/y/releases/download/v1.2/LagScope-viewer.apk\","
      + "\"digest\":\"sha256:" + "a".repeat(64) + "\"}"
      + "]}";

    public static void main(String[] args) {
        System.out.println("Updater.parseLatest");
        Updater.Release r = Updater.parseLatest(JSON);
        eq("reads the version without its v", r.version, "1.2");
        eq("picks the APK, not the Windows installer",
           r.url, "https://github.com/x/y/releases/download/v1.2/LagScope-viewer.apk");
        eq("reads that asset's digest, not its neighbour's", r.sha256, "a".repeat(64));
        eq("reads that asset's size", r.size, 66345L);
        ok("is installable", r.installable());

        System.out.println("\nUpdater.parseLatest declines");
        Updater.Release none = Updater.parseLatest(
            "{\"tag_name\":\"v9\",\"assets\":[{\"name\":\"other.zip\","
          + "\"browser_download_url\":\"https://github.com/a\",\"size\":1}]}");
        ok("a release with no APK offers nothing", !none.hasApk());
        eq("but its version is still read", none.version, "9");

        Updater.Release bare = Updater.parseLatest(
            "{\"tag_name\":\"v9\",\"assets\":[{\"name\":\"LagScope-viewer.apk\","
          + "\"browser_download_url\":\"https://github.com/a/b.apk\",\"size\":1}]}");
        ok("an APK with no digest is found", bare.hasApk());
        ok("but is NOT installable without one", !bare.installable());

        ok("junk is not a crash", !Updater.parseLatest("not json").hasApk());
        ok("null is not a crash", !Updater.parseLatest(null).hasApk());

        System.out.println("\nUpdater.hostAllowed");
        ok("a github release URL",
           Updater.hostAllowed("https://github.com/x/y/releases/download/v1/a.apk"));
        ok("the release asset CDN",
           Updater.hostAllowed("https://objects.githubusercontent.com/x"));
        ok("plain http is refused",
           !Updater.hostAllowed("http://github.com/x/y.apk"));
        ok("a lookalike host is refused",
           !Updater.hostAllowed("https://github.com.evil.example/x.apk"));
        ok("userinfo cannot smuggle a host past the check",
           !Updater.hostAllowed("https://github.com@evil.example/x.apk"));
        ok("an unrelated host is refused",
           !Updater.hostAllowed("https://evil.example/x.apk"));
        ok("null is refused", !Updater.hostAllowed(null));

        System.out.println("\nUpdater.isNewer");
        ok("1.2 over 1.1", Updater.isNewer("1.2", "1.1"));
        ok("1.10 over 1.9 (numbers, not text)", Updater.isNewer("1.10", "1.9"));
        ok("2.0 over 1.99", Updater.isNewer("2.0", "1.99"));
        ok("1.1 is not newer than 1.1", !Updater.isNewer("1.1", "1.1"));
        ok("1.1 equals 1.1.0", !Updater.isNewer("1.1", "1.1.0"));
        ok("1.1.1 beats 1.1", Updater.isNewer("1.1.1", "1.1"));
        ok("older is not newer", !Updater.isNewer("1.0", "1.1"));
        ok("a v prefix does not confuse it", Updater.isNewer("v1.2", "1.1"));
        ok("unreadable is never an upgrade", !Updater.isNewer("garbage", "1.1"));
        ok("null is never an upgrade", !Updater.isNewer(null, "1.1"));

        System.out.println("\nUpdater.hex");
        eq("bytes to lowercase hex",
           Updater.hex(new byte[]{0x00, 0x0f, (byte) 0xa1, (byte) 0xff}), "000fa1ff");

        System.out.println(failed == 0 ? "\nall passed" : "\n" + failed + " failed");
        System.exit(failed == 0 ? 0 : 1);
    }
}
