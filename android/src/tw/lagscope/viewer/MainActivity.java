package tw.lagscope.viewer;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
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
 */
public class MainActivity extends Activity {

    private static final String PREFS = "lagscope";
    private static final String KEY_URL = "dashboard_url";

    private WebView web;
    private LinearLayout setup;
    private EditText addressField;
    private EditText codeField;
    private TextView status;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        String saved = prefs().getString(KEY_URL, "");
        if (saved.isEmpty()) {
            showSetup(null);
        } else {
            showDashboard(saved);
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    // ---------------------------------------------------------------- pairing
    private void showSetup(String message) {
        setup = new LinearLayout(this);
        setup.setOrientation(LinearLayout.VERTICAL);
        setup.setBackgroundColor(Color.parseColor("#12141A"));
        int pad = dp(24);
        setup.setPadding(pad, dp(48), pad, pad);

        setup.addView(heading(getString(R.string.pair_title)));
        setup.addView(body(getString(R.string.pair_intro)));

        addressField = field(getString(R.string.pair_address_hint),
                             InputType.TYPE_TEXT_VARIATION_URI);
        setup.addView(labelled(getString(R.string.pair_address), addressField));

        codeField = field(getString(R.string.pair_code_hint),
                          InputType.TYPE_CLASS_NUMBER);
        setup.addView(labelled(getString(R.string.pair_code), codeField));

        status = body("");
        status.setTextColor(Color.parseColor("#FF5D5D"));
        status.setVisibility(View.GONE);
        setup.addView(status);

        Button connect = new Button(this);
        connect.setText(R.string.pair_connect);
        connect.setAllCaps(false);
        LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
        cp.topMargin = dp(20);
        connect.setLayoutParams(cp);
        connect.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { pair(); }
        });
        setup.addView(connect);

        setup.addView(body(getString(R.string.pair_where)));

        if (message != null) { setStatus(message); }

        ScrollView scroller = new ScrollView(this);
        scroller.setBackgroundColor(Color.parseColor("#12141A"));
        scroller.addView(setup);
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
        web.setBackgroundColor(Color.parseColor("#12141A"));

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                        WebResourceError error) {
                // A phone that has wandered onto mobile data cannot reach a PC
                // on the home network, and that is the usual cause - so say so
                // rather than showing the browser's blank error page.
                if (request != null && request.isForMainFrame()) {
                    showSetup(getString(R.string.err_unreachable));
                }
            }
        });

        setContentView(web);
        // A monitor that sleeps after thirty seconds is not much of a monitor.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web.loadUrl(url);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    // ------------------------------------------------------------------- menu
    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, R.string.menu_reload);
        menu.add(0, 2, 0, R.string.menu_repair);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == 1) {
            if (web != null) { web.reload(); }
            return true;
        }
        if (item.getItemId() == 2) {
            prefs().edit().remove(KEY_URL).apply();
            if (web != null) { web.destroy(); web = null; }
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            showSetup(null);
            Toast.makeText(this, R.string.toast_forgotten, Toast.LENGTH_SHORT).show();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    // ------------------------------------------------------------- small views
    private int dp(int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                                               getResources().getDisplayMetrics());
    }

    private TextView heading(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(Color.parseColor("#F4F6FB"));
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
        view.setGravity(Gravity.START);
        return view;
    }

    private TextView body(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(Color.parseColor("#9AA3B5"));
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(12);
        view.setLayoutParams(lp);
        return view;
    }

    private EditText field(String hint, int inputType) {
        EditText edit = new EditText(this);
        edit.setHint(hint);
        edit.setInputType(inputType);
        edit.setSingleLine(true);
        edit.setTextColor(Color.parseColor("#F4F6FB"));
        edit.setHintTextColor(Color.parseColor("#5B6376"));
        return edit;
    }

    private View labelled(String label, EditText edit) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(18);
        box.setLayoutParams(lp);

        TextView caption = new TextView(this);
        caption.setText(label);
        caption.setTextColor(Color.parseColor("#9AA3B5"));
        caption.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        box.addView(caption);
        box.addView(edit);
        return box;
    }
}
