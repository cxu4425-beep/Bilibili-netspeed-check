package tw.lagscope.viewer;

/**
 * Why the PC cannot be reached, when it cannot be reached.
 *
 * "連不到你的電腦" is this app's most common failure and it has one dominant
 * cause: the phone wandered onto mobile data. A private address - 192.168.x,
 * 10.x, 172.16-31.x - is not routable from the carrier's network, so when the
 * phone is on mobile data and the saved dashboard lives on one of those, the
 * cause is not a guess. It is the only possible answer, and saying it beats
 * telling someone to check things that are already fine.
 *
 * Reading which transport is in use needs ACCESS_NETWORK_STATE, a normal
 * permission granted at install time. Nothing here prompts anyone. Reading the
 * *name* of the Wi-Fi would be a different matter - since Android 8 that needs
 * location permission, and since Android 10 location switched on as well -
 * which is a lot to ask for a network name, so this does not ask.
 *
 * No Android types, so it can be tested on a plain JVM.
 */
public final class NetworkAdvice {

    public static final int TRANSPORT_NONE = 0;
    public static final int TRANSPORT_WIFI = 1;
    public static final int TRANSPORT_MOBILE = 2;
    public static final int TRANSPORT_OTHER = 3;

    /** No network at all: nothing else is worth saying. */
    public static final String REASON_NO_NETWORK = "no_network";
    /** On mobile data, aimed at an address only reachable from the LAN. */
    public static final String REASON_MOBILE_PRIVATE = "mobile_private";
    /** On mobile data. Probably the cause, but not provably so. */
    public static final String REASON_MOBILE = "mobile";
    /** On Wi-Fi and still unreachable: the usual suspects instead. */
    public static final String REASON_WIFI = "wifi";
    public static final String REASON_UNKNOWN = "unknown";

    private NetworkAdvice() { }

    public static String explain(int transport, String dashboardUrl) {
        if (transport == TRANSPORT_NONE) {
            return REASON_NO_NETWORK;
        }
        if (transport == TRANSPORT_MOBILE) {
            return isPrivateAddress(host(dashboardUrl)) ? REASON_MOBILE_PRIVATE : REASON_MOBILE;
        }
        if (transport == TRANSPORT_WIFI) {
            return REASON_WIFI;
        }
        return REASON_UNKNOWN;
    }

    /** The host out of a URL, without scheme, userinfo, port or path. */
    public static String host(String url) {
        if (url == null) {
            return "";
        }
        String rest = url.trim();
        int scheme = rest.indexOf("://");
        if (scheme >= 0) {
            rest = rest.substring(scheme + 3);
        }
        int slash = rest.indexOf('/');
        if (slash >= 0) { rest = rest.substring(0, slash); }
        int question = rest.indexOf('?');
        if (question >= 0) { rest = rest.substring(0, question); }
        int at = rest.indexOf('@');
        if (at >= 0) { rest = rest.substring(at + 1); }
        int colon = rest.lastIndexOf(':');
        if (colon >= 0 && rest.indexOf(':') == colon) {     // a port, not IPv6
            rest = rest.substring(0, colon);
        }
        return rest.trim().toLowerCase();
    }

    /**
     * Whether an address can only be reached from inside the same network.
     *
     * RFC 1918 plus link-local. Deliberately narrow: claiming an address is
     * unreachable when it is not would send someone chasing the wrong thing,
     * so anything unrecognised - a hostname, a public IP - is treated as
     * reachable and the weaker message is used instead.
     */
    public static boolean isPrivateAddress(String host) {
        if (host == null || host.isEmpty()) {
            return false;
        }
        if (host.equals("localhost")) {
            return true;
        }
        String[] parts = host.split("\\.");
        if (parts.length != 4) {
            return false;
        }
        int[] octets = new int[4];
        for (int i = 0; i < 4; i++) {
            try {
                octets[i] = Integer.parseInt(parts[i]);
            } catch (NumberFormatException e) {
                return false;               // not an IPv4 address at all
            }
            if (octets[i] < 0 || octets[i] > 255) {
                return false;
            }
        }
        if (octets[0] == 10 || octets[0] == 127) {
            return true;
        }
        if (octets[0] == 192 && octets[1] == 168) {
            return true;
        }
        if (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) {
            return true;
        }
        // 169.254.x.x - what a device gives itself when DHCP failed.
        return octets[0] == 169 && octets[1] == 254;
    }
}
