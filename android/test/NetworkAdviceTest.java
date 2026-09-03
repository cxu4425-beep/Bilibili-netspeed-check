import tw.lagscope.viewer.NetworkAdvice;

/**
 * The point of this is to stop the app telling someone to check their Wi-Fi
 * when the phone is on mobile data - and, just as important, to stop it
 * claiming mobile data is the cause when it provably is not.
 */
public class NetworkAdviceTest {

    private static int checks = 0;
    private static int failures = 0;

    private static void check(String what, boolean ok) {
        checks++;
        if (!ok) { failures++; System.out.println("FAIL: " + what); }
    }

    private static void same(String what, String expected, String actual) {
        check(what + " (expected " + expected + ", got " + actual + ")",
              expected.equals(actual));
    }

    public static void main(String[] args) {
        String lan = "http://192.168.1.50:23125/?code=1234";

        same("no network beats every other explanation",
             NetworkAdvice.REASON_NO_NETWORK,
             NetworkAdvice.explain(NetworkAdvice.TRANSPORT_NONE, lan));

        // A private address is not routable from a carrier network, so this
        // is the one case where the cause is certain rather than likely.
        same("mobile data plus a LAN address is provably the cause",
             NetworkAdvice.REASON_MOBILE_PRIVATE,
             NetworkAdvice.explain(NetworkAdvice.TRANSPORT_MOBILE, lan));

        same("mobile data plus a public address is only probable",
             NetworkAdvice.REASON_MOBILE,
             NetworkAdvice.explain(NetworkAdvice.TRANSPORT_MOBILE,
                                   "http://example.com:23125/"));

        same("on Wi-Fi and still failing means something else",
             NetworkAdvice.REASON_WIFI,
             NetworkAdvice.explain(NetworkAdvice.TRANSPORT_WIFI, lan));

        same("an unrecognised transport does not invent a cause",
             NetworkAdvice.REASON_UNKNOWN,
             NetworkAdvice.explain(NetworkAdvice.TRANSPORT_OTHER, lan));

        // --- pulling the host out of what pairing actually stores
        same("host from a full url", "192.168.1.50", NetworkAdvice.host(lan));
        same("host without a scheme", "10.0.0.8", NetworkAdvice.host("10.0.0.8:23125"));
        same("host with userinfo", "192.168.0.2",
             NetworkAdvice.host("http://user:pw@192.168.0.2/x"));
        same("hostname kept as is", "mypc.local",
             NetworkAdvice.host("http://MyPC.local/dash"));
        same("empty url", "", NetworkAdvice.host(null));

        // --- what counts as only-reachable-from-here
        String[] privateOnes = {"192.168.1.1", "10.255.0.1", "172.16.0.1",
                                "172.31.255.254", "127.0.0.1", "169.254.1.1",
                                "localhost"};
        for (String host : privateOnes) {
            check(host + " is LAN-only", NetworkAdvice.isPrivateAddress(host));
        }

        // Narrow on purpose: calling something unreachable when it is not
        // would send someone chasing the wrong thing.
        String[] publicOnes = {"172.15.0.1", "172.32.0.1", "8.8.8.8",
                               "193.168.1.1", "example.com", "", "1.2.3",
                               "999.1.1.1", "192.168.one.1"};
        for (String host : publicOnes) {
            check(host + " is not treated as LAN-only",
                  !NetworkAdvice.isPrivateAddress(host));
        }

        System.out.println(failures == 0
            ? "NetworkAdviceTest: " + checks + " checks passed"
            : "NetworkAdviceTest: " + failures + " of " + checks + " FAILED");
        if (failures > 0) { System.exit(1); }
    }
}
