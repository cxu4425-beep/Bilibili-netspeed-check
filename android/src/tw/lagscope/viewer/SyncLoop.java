package tw.lagscope.viewer;

/**
 * The clock behind the Bluetooth calibration: when to click, when to flash.
 *
 * The desktop app measures everything up to the picture. Anyone listening on
 * Bluetooth has one more delay after that, and no operating system will report
 * it - Android's BluetoothCodecConfig, which knows the codec and therefore
 * most of the answer, needs a permission only system apps are granted. So the
 * number is measured instead, by ear: a click plays, the screen flashes a
 * settable amount later, and the person moves one until the two coincide. What
 * they dialled in is how much later the sound arrived than the picture.
 *
 * This class holds no Android types on purpose. The machine this was written
 * on has no phone and no emulator, so anything that cannot run on a bare JVM
 * cannot be checked at all - and the timing is the one part of the feature
 * that has to be exactly right, because the person reads their answer straight
 * off it.
 *
 * The number it produces is about *this phone*, not about the PC being
 * watched: the two have different audio paths. The screen says so.
 */
public final class SyncLoop {

    /** One click and one flash per cycle, with quiet either side. */
    public static final int PERIOD_MS = 1200;
    /** Long enough to see without smearing into the next cycle. */
    public static final int FLASH_MS = 60;
    /** Past anything a real headset does; beyond this it is a slip, not a value. */
    public static final int MAX_OFFSET_MS = 400;

    private int offsetMs;
    private long cycleStart;
    private boolean started;
    private boolean clicked;
    private boolean lit;

    public void reset(long now) {
        cycleStart = now;
        started = true;
        clicked = false;
        lit = false;
    }

    public void setOffsetMs(int value) {
        if (value < 0) { value = 0; }
        if (value > MAX_OFFSET_MS) { value = MAX_OFFSET_MS; }
        offsetMs = value;
    }

    public int offsetMs() {
        return offsetMs;
    }

    public boolean isLit() {
        return lit;
    }

    /**
     * Advance the loop to {@code now}. Returns true when a click should be
     * played at this instant - the caller plays it, so that nothing here has
     * to know what a sound is.
     */
    public boolean tick(long now) {
        if (!started) {
            reset(now);
        }
        long elapsed = now - cycleStart;
        if (elapsed < 0 || elapsed >= PERIOD_MS) {
            // Restart from now rather than subtracting a period: a cycle that
            // ran long because the phone was busy should not push every later
            // cycle out behind it.
            reset(now);
            elapsed = 0;
        }

        boolean click = false;
        if (!clicked) {
            clicked = true;
            click = true;
        }
        lit = elapsed >= offsetMs && elapsed < offsetMs + FLASH_MS;
        return click;
    }

    public void stop() {
        started = false;
        lit = false;
    }
}
