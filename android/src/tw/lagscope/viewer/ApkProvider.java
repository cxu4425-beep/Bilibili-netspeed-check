package tw.lagscope.viewer;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Hands the downloaded APK to the package installer.
 *
 * Since Android 7 an app may not pass a file:// URI to another app, so the
 * installer has to be given a content:// one. The usual answer is AndroidX's
 * FileProvider, which lives on Google's Maven - unreachable from the machine
 * this was built on - so this is the same idea in the few lines it actually
 * needs.
 *
 * It is deliberately narrower than FileProvider: it serves exactly one file,
 * the update this app just downloaded and verified, and ignores the path in
 * the URI entirely. A provider that resolves a caller-supplied path is a
 * provider that can be talked into serving something else; this one has
 * nothing to be talked into.
 */
public class ApkProvider extends ContentProvider {

    public static final String AUTHORITY = "tw.lagscope.viewer.updates";
    private static final String FILE_NAME = "update.apk";

    /** The one file this provider will ever serve. */
    public static File updateFile(android.content.Context context) {
        File dir = new File(context.getCacheDir(), "updates");
        if (!dir.exists()) { dir.mkdirs(); }
        return new File(dir, FILE_NAME);
    }

    public static Uri uriFor() {
        return Uri.parse("content://" + AUTHORITY + "/" + FILE_NAME);
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        File file = updateFile(getContext());
        if (!file.exists()) {
            throw new FileNotFoundException("no update downloaded");
        }
        // Read only, whatever was asked for: the installer never needs to write.
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        return "application/vnd.android.package-archive";
    }

    /** The installer asks for the name and size before it opens anything. */
    @Override
    public Cursor query(Uri uri, String[] projection, String selection,
                        String[] selectionArgs, String sortOrder) {
        File file = updateFile(getContext());
        String[] columns = {OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
        MatrixCursor cursor = new MatrixCursor(columns, 1);
        cursor.addRow(new Object[]{FILE_NAME, file.length()});
        return cursor;
    }

    // Nothing else is offered. An update file is written by this app and read
    // by the installer; no other operation has a legitimate caller.
    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException();
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException();
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        throw new UnsupportedOperationException();
    }
}
