package tw.lagscope.viewer;

/**
 * Turning what someone types into the dashboard URL.
 *
 * Kept apart from the Activity because it is the only part with a right and a
 * wrong answer, and separating it is what makes it testable without a phone -
 * this was written on a machine with no Android device and no emulator, so
 * anything that cannot be checked here cannot be checked at all.
 */
public final class Pairing {

    /** The port the desktop app serves the dashboard on by default. */
    public static final int DEFAULT_PORT = 23125;

    private Pairing() { }

    /** Accepts a pasted dashboard URL as readily as a host and a code. */
    public static String buildUrl(String address, String code) {
        String host = address == null ? "" : address.trim();
        String pin = code == null ? "" : code.trim();
        if (host.isEmpty()) {
            return "";
        }

        // A pasted URL already carries everything, including its own code;
        // appending a second one would produce a request the server rejects.
        if (host.startsWith("http://") || host.startsWith("https://")) {
            if (pin.isEmpty() || host.contains("code=")) {
                return host;
            }
            return host + (host.contains("?") ? "&" : "?") + "code=" + pin;
        }

        // A bare host, or host:port. Filling in the default port removes the
        // detail that is easiest to get wrong when copying by hand.
        if (host.indexOf(':') < 0) {
            host = host + ":" + DEFAULT_PORT;
        }
        String url = "http://" + host + "/";
        if (!pin.isEmpty()) {
            url = url + "?code=" + pin;
        }
        return url;
    }
}
