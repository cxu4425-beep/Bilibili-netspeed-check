package tw.lagscope.viewer;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.ProgressDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup.LayoutParams;
import android.view.WindowManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * A viewer for the dashboard the desktop app already serves on the local
 * network. It is deliberately not a second LagScope: Android stopped letting
 * an app read other apps' connections in Android 10, so a phone cannot do the
 * measuring - only the machine being measured can. This shows that machine's
 * numbers, live, on the phone in your hand.
 *
 * There is no account and no server in the middle. The phone talks straight to
 * the PC, so the desktop app's promise that nothing leaves the machine still
 * holds. "Signing in" here is pairing: the address of your PC and the access
 * code it prints, remembered so it is asked once rather than every time.
 *
 * The colours come from res/values/colors.xml, which sync_theme.py generates
 * from the desktop app's own palette - so "the same as the PC" is maintained
 * by a script rather than by remembering.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "lagscope";
    private static final String KEY_URL = "dashboard_url";
    private static final String KEY_LAST_CHECK = "last_update_check";
    private static final long CHECK_INTERVAL_MS = 24L * 60 * 60 * 1000;

    private WebView web;
    private EditText addressField;
    private EditText codeField;
    private TextView status;
    private final Handler main = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        String saved = prefs().getString(KEY_URL, "");
        if (saved.isEmpty()) {
            showSetup(null);
        } else {
            showDashboard(saved);
            maybeCheckForUpdate();
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private int colour(int id) {
        return getResources().getColor(id);
    }

    // ---------------------------------------------------------------- pairing
    private void showSetup(String message) {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        page.setPadding(pad, dp(40), pad, pad);

        page.addView(heading(getString(R.string.pair_title)));
        page.addView(body(getString(R.string.pair_intro)));

        LinearLayout card = card();
        addressField = field(getString(R.string.pair_address_hint),
                             InputType.TYPE_TEXT_VARIATION_URI);
        card.addView(labelled(getString(R.string.pair_address), addressField));
        codeField = field(getString(R.string.pair_code_hint), InputType.TYPE_CLASS_NUMBER);
        card.addView(labelled(getString(R.string.pair_code), codeField));
        page.addView(card);

        status = body("");
        status.setTextColor(colour(R.color.bad));
        status.setVisibility(View.GONE);
        page.addView(status);

        page.addView(accentButton(getString(R.string.pair_connect), new View.OnClickListener() {
            @Override public void onClick(View v) { pair(); }
        }));
        page.addView(body(getString(R.string.pair_where)));

        if (message != null) { setStatus(message); }

        ScrollView scroller = new ScrollView(this);
        scroller.setBackgroundColor(colour(R.color.background));
        scroller.addView(page);
        setContentView(scroller);
    }

    private void setStatus(String message) {
        if (status == null) { return; }
        status.setText(message);
        status.setVisibility(View.VISIBLE);
    }

    private void pair() {
        String url = Pairing.buildUrl(addressField.getText().toString(),
                                      codeField.getText().toString());
        if (url.isEmpty()) {
            setStatus(getString(R.string.pair_need_address));
            return;
        }
        prefs().edit().putString(KEY_URL, url).apply();
        showDashboard(url);
    }

    // -------------------------------------------------------------- dashboard
    private void showDashboard(final String url) {
        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);        // the dashboard draws with it
        settings.setDomStorageEnabled(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);   // it is live data
        web.setBackgroundColor(colour(R.color.background));

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                        WebResourceError error) {
                // A phone that has wandered onto mobile data cannot reach a PC
                // on the home network, and that is the usual cause - so say so
                // rather than showing the browser's blank error page.
                if (request != null && request.isForMainFrame()) {
                    showSetup(unreachableMessage());
                }
            }
        });

        setContentView(web);
        // A monitor that sleeps after thirty seconds is not much of a monitor.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web.loadUrl(url);
    }

    /**
     * Why the PC could not be reached, named as precisely as the facts allow.
     *
     * The old message told everyone to check the same two things. The usual
     * cause is the phone having wandered onto mobile data, and when the
     * dashboard lives on a private address that is not a guess - a carrier
     * network cannot route to 192.168.x at all.
     */
    private String unreachableMessage() {
        String reason = NetworkAdvice.explain(currentTransport(),
                                              prefs().getString(KEY_URL, ""));
        if (NetworkAdvice.REASON_NO_NETWORK.equals(reason)) {
            return getString(R.string.err_no_network);
        }
        if (NetworkAdvice.REASON_MOBILE_PRIVATE.equals(reason)) {
            return getString(R.string.err_mobile_private);
        }
        if (NetworkAdvice.REASON_MOBILE.equals(reason)) {
            return getString(R.string.err_mobile);
        }
        return getString(R.string.err_unreachable);
    }

    /**
     * Which kind of network is carrying traffic right now.
     *
     * Only ACCESS_NETWORK_STATE, which is granted at install and prompts
     * nobody. The Wi-Fi's *name* is deliberately not read: that has needed
     * location permission since Android 8, and location switched on since
     * Android 10, which is far too much to ask for a network name.
     */
    private int currentTransport() {
        try {
            ConnectivityManager manager =
                    (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            if (manager == null) { return NetworkAdvice.TRANSPORT_OTHER; }
            Network active = manager.getActiveNetwork();
            if (active == null) { return NetworkAdvice.TRANSPORT_NONE; }
            NetworkCapabilities caps = manager.getNetworkCapabilities(active);
            if (caps == null) { return NetworkAdvice.TRANSPORT_NONE; }
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                return NetworkAdvice.TRANSPORT_WIFI;
            }
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) {
                return NetworkAdvice.TRANSPORT_MOBILE;
            }
            return NetworkAdvice.TRANSPORT_OTHER;
        } catch (Exception e) {
            // Never let a diagnosis crash the thing it is diagnosing.
            return NetworkAdvice.TRANSPORT_OTHER;
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    // ------------------------------------------------------------- updating
    /** Once a day at most, and never in a way the person has to wait for. */
    private void maybeCheckForUpdate() {
        long last = prefs().getLong(KEY_LAST_CHECK, 0);
        long now = System.currentTimeMillis();
        if (last > 0 && now - last < CHECK_INTERVAL_MS && now >= last) {
            return;
        }
        prefs().edit().putLong(KEY_LAST_CHECK, now).apply();
        checkForUpdate(false);
    }

    private void checkForUpdate(final boolean loud) {
        new Thread(new Runnable() {
            @Override public void run() {
                final Updater.Release release = fetchLatest();
                main.post(new Runnable() {
                    @Override public void run() { onLatest(release, loud); }
                });
            }
        }).start();
    }

    private Updater.Release fetchLatest() {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(Updater.RELEASES_API).openConnection();
            connection.setRequestProperty("Accept", "application/vnd.github+json");
            connection.setRequestProperty("User-Agent", "LagScope-viewer/" + versionName());
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(8000);
            InputStream in = connection.getInputStream();
            StringBuilder out = new StringBuilder();
            byte[] buffer = new byte[8192];
            int read;
            int total = 0;
            while ((read = in.read(buffer)) > 0 && total < 1024 * 1024) {
                out.append(new String(buffer, 0, read, "UTF-8"));
                total += read;
            }
            in.close();
            return Updater.parseLatest(out.toString());
        } catch (Exception e) {
            // Offline, rate limited, behind a captive portal: all normal, and
            // none of them are worth interrupting someone over.
            return null;
        } finally {
            if (connection != null) { connection.disconnect(); }
        }
    }

    private void onLatest(Updater.Release release, boolean loud) {
        if (release == null || !Updater.isNewer(release.version, versionName())) {
            if (loud) {
                Toast.makeText(this, R.string.update_none, Toast.LENGTH_SHORT).show();
            }
            return;
        }
        if (!release.installable()) {
            // No published checksum, or an unexpected host. Offer the page and
            // let a person decide, rather than installing something unverified.
            openPage();
            return;
        }
        confirm(release);
    }

    private void confirm(final Updater.Release release) {
        new AlertDialog.Builder(this)
            .setTitle(getString(R.string.update_title, release.version))
            .setMessage(getString(R.string.update_body,
                                  Math.max(1, release.size / 1024)))
            .setPositiveButton(R.string.update_now,
                new android.content.DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(android.content.DialogInterface d, int which) {
                        install(release);
                    }
                })
            .setNegativeButton(R.string.update_later, null)
            .show();
    }

    private void install(final Updater.Release release) {
        final ProgressDialog progress = new ProgressDialog(this);
        progress.setMessage(getString(R.string.update_downloading));
        progress.setCancelable(false);
        progress.show();

        new Thread(new Runnable() {
            @Override public void run() {
                final String error = download(release);
                main.post(new Runnable() {
                    @Override public void run() {
                        progress.dismiss();
                        if (error == null) {
                            launchInstaller();
                        } else {
                            Toast.makeText(MainActivity.this,
                                getString(R.string.update_failed, error),
                                Toast.LENGTH_LONG).show();
                            openPage();
                        }
                    }
                });
            }
        }).start();
    }

    /** Returns null on success, or a short reason. Nothing unverified is kept. */
    private String download(Updater.Release release) {
        File target = ApkProvider.updateFile(this);
        File partial = new File(target.getParentFile(), target.getName() + ".part");
        HttpURLConnection connection = null;
        try {
            if (!Updater.hostAllowed(release.url)) { return "untrusted-host"; }
            connection = (HttpURLConnection) new URL(release.url).openConnection();
            connection.setInstanceFollowRedirects(true);
            connection.setConnectTimeout(15000);
            connection.setReadTimeout(30000);
            if (!Updater.hostAllowed(connection.getURL().toString())) {
                return "untrusted-redirect";     // a redirect off GitHub is off the checks
            }

            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            InputStream in = connection.getInputStream();
            FileOutputStream out = new FileOutputStream(partial);
            byte[] buffer = new byte[16384];
            long written = 0;
            int read;
            while ((read = in.read(buffer)) > 0) {
                written += read;
                if (written > 64L * 1024 * 1024) { return "too-large"; }
                digest.update(buffer, 0, read);
                out.write(buffer, 0, read);
            }
            out.close();
            in.close();

            if (release.size > 0 && written != release.size) { return "wrong-size"; }
            if (!Updater.hex(digest.digest()).equals(release.sha256)) {
                // The published hash is the only thing between a download and
                // the package installer, so a mismatch discards it.
                return "checksum-mismatch";
            }
            if (target.exists()) { target.delete(); }
            return partial.renameTo(target) ? null : "rename-failed";
        } catch (Exception e) {
            return e.getClass().getSimpleName();
        } finally {
            if (connection != null) { connection.disconnect(); }
            if (partial.exists()) { partial.delete(); }
        }
    }

    private void launchInstaller() {
        // Since Android 8 an app needs permission before it can ask to install
        // anything; sending someone to the setting is friendlier than an
        // installer that silently refuses.
        if (!canInstallPackages()) {
            new AlertDialog.Builder(this)
                .setMessage(R.string.update_permission)
                .setPositiveButton(R.string.update_settings,
                    new android.content.DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(android.content.DialogInterface d, int which) {
                            startActivity(new Intent(ACTION_UNKNOWN_APP_SOURCES,
                                          Uri.parse("package:" + getPackageName())));
                        }
                    })
                .setNegativeButton(R.string.update_later, null)
                .show();
            return;
        }
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(ApkProvider.uriFor(),
                              "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                        | Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }

    // Compiled against API 23's android.jar, because that is the newest one
    // packaged for this build machine. These two arrived in API 26, so they
    // are reached by name rather than by symbol - the alternative is not
    // supporting Android 8 and later at all.
    private static final int ANDROID_8 = 26;
    private static final String ACTION_UNKNOWN_APP_SOURCES =
            "android.settings.MANAGE_UNKNOWN_APP_SOURCES";

    private boolean canInstallPackages() {
        if (Build.VERSION.SDK_INT < ANDROID_8) {
            return true;                    // no such restriction before 8
        }
        try {
            Object allowed = android.content.pm.PackageManager.class
                    .getMethod("canRequestPackageInstalls")
                    .invoke(getPackageManager());
            return Boolean.TRUE.equals(allowed);
        } catch (Exception e) {
            // If it cannot be asked, let the installer itself decide rather
            // than blocking an update over a reflection failure.
            return true;
        }
    }

    private void openPage() {
        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Updater.RELEASES_PAGE)));
    }

    private String versionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "0";
        }
    }

    // ------------------------------------------------------------------- menu
    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, R.string.menu_reload);
        menu.add(0, 2, 0, R.string.menu_update);
        menu.add(0, 3, 0, R.string.menu_audio);
        menu.add(0, 4, 0, R.string.menu_repair);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()) {
            case 1:
                if (web != null) { web.reload(); }
                return true;
            case 2:
                Toast.makeText(this, R.string.update_checking, Toast.LENGTH_SHORT).show();
                checkForUpdate(true);
                return true;
            case 3:
                startActivity(new Intent(this, AudioSyncActivity.class));
                return true;
            case 4:
                prefs().edit().remove(KEY_URL).apply();
                if (web != null) { web.destroy(); web = null; }
                getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                showSetup(null);
                Toast.makeText(this, R.string.toast_forgotten, Toast.LENGTH_SHORT).show();
                return true;
            default:
                return super.onOptionsItemSelected(item);
        }
    }

    // ------------------------------------------------------------- small views
    private int dp(int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                                               getResources().getDisplayMetrics());
    }

    /** The desktop dashboard's card: a raised surface, hairline border, 14dp. */
    private LinearLayout card() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(colour(R.color.surface));
        shape.setStroke(dp(1), colour(R.color.border));
        shape.setCornerRadius(dp(14));
        box.setBackground(shape);
        int pad = dp(16);
        box.setPadding(pad, dp(4), pad, pad);
        box.setLayoutParams(spaced(dp(20)));
        return box;
    }

    private Button accentButton(String text, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextColor(Color.WHITE);
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(colour(R.color.accent));
        shape.setCornerRadius(dp(12));
        button.setBackground(shape);
        button.setLayoutParams(spaced(dp(18)));
        button.setOnClickListener(listener);
        return button;
    }

    private LinearLayout.LayoutParams spaced(int topMargin) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
        lp.topMargin = topMargin;
        return lp;
    }

    private TextView heading(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(colour(R.color.foreground));
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
        return view;
    }

    private TextView body(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(colour(R.color.muted));
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        view.setLineSpacing(dp(4), 1f);
        view.setLayoutParams(spaced(dp(12)));
        return view;
    }

    private EditText field(String hint, int inputType) {
        EditText edit = new EditText(this);
        edit.setHint(hint);
        edit.setInputType(inputType);
        edit.setSingleLine(true);
        edit.setTextColor(colour(R.color.foreground));
        edit.setHintTextColor(colour(R.color.muted));
        return edit;
    }

    private View labelled(String label, EditText edit) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setLayoutParams(spaced(dp(14)));

        TextView caption = new TextView(this);
        caption.setText(label);
        caption.setTextColor(colour(R.color.muted));
        caption.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        box.addView(caption);
        box.addView(edit);
        return box;
    }
}
