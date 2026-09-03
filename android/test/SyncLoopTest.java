import tw.lagscope.viewer.SyncLoop;

/**
 * The calibration is only as honest as this loop: the person reads their
 * answer off the slider believing the flash really was that much later than
 * the click. If it was not, the number they save is wrong and nothing about it
 * looks wrong.
 */
public class SyncLoopTest {

    private static int checks = 0;
    private static int failures = 0;

    private static void check(String what, boolean ok) {
        checks++;
        if (!ok) { failures++; System.out.println("FAIL: " + what); }
    }

    /** Step a whole cycle a millisecond at a time and note what happened when. */
    private static int[] runCycle(int offset) {
        SyncLoop loop = new SyncLoop();
        loop.setOffsetMs(offset);
        loop.reset(0);
        int clickAt = -1, onAt = -1, offAt = -1;
        boolean wasLit = false;
        for (int now = 0; now < SyncLoop.PERIOD_MS; now++) {
            if (loop.tick(now) && clickAt < 0) { clickAt = now; }
            if (loop.isLit() && !wasLit) { onAt = now; }
            if (wasLit && !loop.isLit() && offAt < 0) { offAt = now; }
            wasLit = loop.isLit();
        }
        return new int[]{clickAt, onAt, offAt};
    }

    public static void main(String[] args) {
        for (int offset : new int[]{0, 40, 150, 250, SyncLoop.MAX_OFFSET_MS}) {
            int[] seen = runCycle(offset);
            check("click at the start of the cycle (offset " + offset + ")", seen[0] == 0);
            check("flash exactly " + offset + " ms later", seen[1] == offset);
            check("flash lasts " + SyncLoop.FLASH_MS + " ms (offset " + offset + ")",
                  seen[2] == offset + SyncLoop.FLASH_MS);
        }

        // The cycle has to have room for the largest offset, or the flash a
        // person dialled in would simply never be shown.
        check("period leaves room for the largest offset",
              SyncLoop.MAX_OFFSET_MS + SyncLoop.FLASH_MS < SyncLoop.PERIOD_MS);

        SyncLoop loop = new SyncLoop();
        loop.setOffsetMs(100);
        loop.reset(0);
        int clicks = 0;
        for (int now = 0; now <= SyncLoop.PERIOD_MS * 3; now++) {
            if (loop.tick(now)) { clicks++; }
        }
        check("one click per cycle, repeating", clicks == 4);

        loop.setOffsetMs(-50);
        check("negative offsets are refused", loop.offsetMs() == 0);
        loop.setOffsetMs(99999);
        check("silly offsets are capped", loop.offsetMs() == SyncLoop.MAX_OFFSET_MS);

        // A phone whose clock jumped backwards (or a first tick before any
        // reset) must not freeze the loop or flash forever.
        SyncLoop jumpy = new SyncLoop();
        jumpy.setOffsetMs(100);
        jumpy.reset(10_000);
        jumpy.tick(9_000);
        check("a backwards clock restarts the cycle", !jumpy.isLit());
        check("and the next click still comes", jumpy.tick(9_000 + SyncLoop.PERIOD_MS));

        SyncLoop fresh = new SyncLoop();
        check("ticking without reset still clicks", fresh.tick(500));

        System.out.println(failures == 0
            ? "SyncLoopTest: " + checks + " checks passed"
            : "SyncLoopTest: " + failures + " of " + checks + " FAILED");
        if (failures > 0) { System.exit(1); }
    }
}
