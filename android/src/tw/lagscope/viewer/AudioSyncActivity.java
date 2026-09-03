package tw.lagscope.viewer;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup.LayoutParams;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

/**
 * Measuring how much later this phone's sound arrives than its picture.
 *
 * The one number the desktop app cannot reach is the last hop: screen to ears.
 * On Bluetooth that is usually 100-250 ms, larger than everything the display
 * adds, and Android will not report it - the codec, which decides most of it,
 * is behind BluetoothCodecConfig and a permission reserved for system apps.
 *
 * So the person measures it. A click plays and the panel flashes a settable
 * amount later; they move the slider until the two land together, and what
 * they dialled in is the answer. SyncLoop holds the timing, which is the part
 * that has to be right, and is unit-tested on a plain JVM because none of this
 * screen can be run on the machine it was written on.
 *
 * This measures *this phone*. The viewer shows a PC's numbers, and the PC has
 * its own audio path and quite possibly its own headphones - so the result is
 * shown here and kept here, never folded into the figures coming from the PC.
 */
public class AudioSyncActivity extends Activity {

    public static final String PREFS = "lagscope";
    public static final String KEY_AUDIO_OFFSET = "audio_offset_ms";

    // Fast enough that the flash lands within a few ms of where it was asked
    // for - well inside the 20-40 ms at which people notice a mismatch at all.
    private static final int TICK_MS = 8;
    private static final int TONE_MS = 60;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final SyncLoop loop = new SyncLoop();

    private TextView panelLabel;
    private TextView readout;
    private Button startButton;
    private SeekBar slider;
    private ToneGenerator tones;
    private boolean running;

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (!running) { return; }
            if (loop.tick(SystemClock.elapsedRealtime())) { click(); }
            setLit(loop.isLit());
            main.postDelayed(this, TICK_MS);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setTitle(R.string.audio_title);

        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        page.setPadding(pad, pad, pad, pad);

        page.addView(body(getString(R.string.audio_intro), false));
        page.addView(body(getString(R.string.audio_steps), true));

        // A plain block, large: the eye reacts to a whole field changing
        // brightness faster than to a small indicator it has to look at.
        LinearLayout.LayoutParams panelSize =
                new LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, dp(170));
        panelSize.topMargin = dp(8);
        panelLabel = new TextView(this);
        panelLabel.setText(R.string.audio_watch_here);
        panelLabel.setGravity(Gravity.CENTER);
        panelLabel.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        panelLabel.setLayoutParams(panelSize);
        page.addView(panelLabel);
        setLit(false);

        readout = new TextView(this);
        readout.setTextSize(TypedValue.COMPLEX_UNIT_SP, 26);
        readout.setTextColor(colour(R.color.foreground));
        readout.setPadding(0, dp(14), 0, dp(4));
        page.addView(readout);

        slider = new SeekBar(this);
        slider.setMax(SyncLoop.MAX_OFFSET_MS);
        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                loop.setOffsetMs(value);
                showValue();
            }
            @Override public void onStartTrackingTouch(SeekBar bar) { }
            @Override public void onStopTrackingTouch(SeekBar bar) { }
        });
        page.addView(slider);

        LinearLayout fine = new LinearLayout(this);
        fine.setOrientation(LinearLayout.HORIZONTAL);
        int[] steps = {-10, -1, 1, 10};
        for (int i = 0; i < steps.length; i++) {
            final int delta = steps[i];
            Button button = new Button(this);
            button.setText(delta > 0 ? "+" + delta : String.valueOf(delta));
            button.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    slider.setProgress(slider.getProgress() + delta);
                }
            });
            fine.addView(button, new LinearLayout.LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f));
        }
        page.addView(fine);

        startButton = new Button(this);
        startButton.setText(R.string.audio_start);
        startButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { toggle(); }
        });
        page.addView(startButton);

        Button save = new Button(this);
        save.setText(R.string.audio_save);
        save.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { save(); }
        });
        page.addView(save);

        page.addView(body(getString(R.string.audio_accuracy), true));
        page.addView(body(getString(R.string.audio_this_phone), true));

        ScrollView scroller = new ScrollView(this);
        scroller.setBackgroundColor(colour(R.color.background));
        scroller.addView(page);
        setContentView(scroller);

        slider.setProgress(prefs().getInt(KEY_AUDIO_OFFSET, 0));
        loop.setOffsetMs(slider.getProgress());
        showValue();
        // A screen that sleeps halfway through the measurement is no use.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    // ------------------------------------------------------------------ run
    private void toggle() {
        if (running) {
            stop();
            return;
        }
        try {
            if (tones == null) {
                tones = new ToneGenerator(AudioManager.STREAM_MUSIC, 90);
            }
        } catch (RuntimeException e) {
            // Some devices refuse a ToneGenerator when the audio path is busy.
            Toast.makeText(this, R.string.audio_unavailable, Toast.LENGTH_LONG).show();
            return;
        }
        running = true;
        startButton.setText(R.string.audio_stop);
        loop.reset(SystemClock.elapsedRealtime());
        main.post(tick);
    }

    private void stop() {
        running = false;
        main.removeCallbacks(tick);
        loop.stop();
        setLit(false);
        startButton.setText(R.string.audio_start);
    }

    private void click() {
        if (tones != null) {
            tones.startTone(ToneGenerator.TONE_PROP_BEEP, TONE_MS);
        }
    }

    private void save() {
        int value = slider.getProgress();
        prefs().edit().putInt(KEY_AUDIO_OFFSET, value).apply();
        Toast.makeText(this, getString(R.string.audio_saved, value), Toast.LENGTH_SHORT).show();
        stop();
        finish();
    }

    @Override
    protected void onPause() {
        // Clicking on into a pocket would be both useless and rude.
        super.onPause();
        stop();
    }

    @Override
    protected void onDestroy() {
        stop();
        if (tones != null) { tones.release(); tones = null; }
        super.onDestroy();
    }

    // --------------------------------------------------------------- views
    private void showValue() {
        readout.setText(getString(R.string.audio_readout, slider.getProgress()));
    }

    private void setLit(boolean lit) {
        GradientDrawable shape = new GradientDrawable();
        shape.setCornerRadius(dp(14));
        shape.setColor(lit ? colour(R.color.accent) : Color.parseColor("#1b1e26"));
        panelLabel.setBackgroundDrawable(shape);
        panelLabel.setTextColor(lit ? Color.parseColor("#0d0f14") : colour(R.color.muted));
    }

    private TextView body(String text, boolean muted) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        view.setTextColor(colour(muted ? R.color.muted : R.color.foreground));
        view.setPadding(0, dp(6), 0, dp(6));
        return view;
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private int colour(int id) {
        return getResources().getColor(id);
    }

    private int dp(int value) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                                               getResources().getDisplayMetrics());
    }
}
