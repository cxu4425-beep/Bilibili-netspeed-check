#!/usr/bin/env bash
# Build the LagScope viewer APK without Gradle.
#
# Gradle would want the Android Gradle Plugin, which lives on Google's Maven -
# unreachable from the machine this was written on. The steps below are what
# AGP does anyway, and for one activity with no libraries they are short:
#
#   aapt   package the manifest and resources, generate R.java
#   javac  compile the Java to class files (targeting 8, which dx understands)
#   dx     convert class files to a Dalvik dex
#   aapt   add the dex into the package
#   zipalign / apksigner   align and sign it so Android will install it
#
# Everything comes from Debian packages except dx, which is vendored in
# tools/ from Maven Central.
set -euo pipefail

cd "$(dirname "$0")"

SDK=${ANDROID_SDK:-/usr/lib/android-sdk}
PLATFORM="$SDK/platforms/android-23/android.jar"
OUT=build
APK_UNSIGNED="$OUT/lagscope-unsigned.apk"
APK_ALIGNED="$OUT/lagscope-aligned.apk"
APK="$OUT/LagScope-viewer.apk"
# NOT inside $OUT: that directory is wiped at the start of every build, so a
# keystore kept there was silently regenerated each time and every APK was
# signed with a different key. Android refuses an update whose signature
# changed, so those builds could not upgrade each other - the failure only
# shows up on a phone, which is where it cannot be seen from here.
KEYSTORE=${KEYSTORE:-keystore/lagscope.jks}
STOREPASS=${STOREPASS:-lagscope}

for tool in aapt zipalign apksigner javac keytool; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done
[ -f "$PLATFORM" ] || { echo "missing android.jar: $PLATFORM" >&2; exit 1; }
[ -f tools/dx.jar ] || { echo "missing tools/dx.jar" >&2; exit 1; }

rm -rf "$OUT"; mkdir -p "$OUT/gen" "$OUT/classes" "$OUT/test"

echo "[1/7] tests (plain JVM)"
# Run first: shipping an APK whose logic was never checked is exactly the
# thing that is hard to notice, since none of it can be run on this machine.
javac -nowarn -encoding UTF-8 -d "$OUT/test" \
  src/tw/lagscope/viewer/Pairing.java src/tw/lagscope/viewer/Updater.java \
  src/tw/lagscope/viewer/SyncLoop.java \
  test/PairingTest.java test/UpdaterTest.java test/SyncLoopTest.java
java -cp "$OUT/test" PairingTest | tail -1
java -cp "$OUT/test" UpdaterTest | tail -1
java -cp "$OUT/test" SyncLoopTest | tail -1

echo "[2/7] aapt: resources + R.java"
aapt package -f -m \
  -J "$OUT/gen" -M AndroidManifest.xml -S res -I "$PLATFORM" \
  -F "$OUT/resources.ap_"

echo "[3/7] javac"
# Android's dex format predates newer class-file versions; 8 is what dx reads.
javac -source 8 -target 8 -nowarn -encoding UTF-8 \
  -bootclasspath "$PLATFORM" -classpath "$PLATFORM" \
  -d "$OUT/classes" \
  $(find src "$OUT/gen" -name '*.java') 2>&1 | grep -v "bootstrap class path" || true

echo "[4/7] dx: classes -> dex"
java -cp tools/dx.jar com.android.dx.command.Main --dex \
  --output="$OUT/classes.dex" "$OUT/classes"

echo "[5/7] package"
cp "$OUT/resources.ap_" "$APK_UNSIGNED"
( cd "$OUT" && aapt add -k "$(basename "$APK_UNSIGNED")" classes.dex >/dev/null )

echo "[6/7] zipalign"
# Alignment must happen before signing: v2 signatures cover the whole archive,
# so aligning afterwards would invalidate them.
zipalign -f 4 "$APK_UNSIGNED" "$APK_ALIGNED"

echo "[7/7] sign"
mkdir -p "$(dirname "$KEYSTORE")"
if [ ! -f "$KEYSTORE" ]; then
  # Self-signed, for sideloading. Keep this file - it is the app's identity.
  # Android refuses an update signed by a different key, so losing it means
  # every user has to uninstall before they can upgrade.
  keytool -genkeypair -v -keystore "$KEYSTORE" -storepass "$STOREPASS" \
    -keypass "$STOREPASS" -alias lagscope -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=LagScope, OU=LagScope, O=LagScope, C=TW" \
    >/dev/null 2>&1
  echo "      generated $KEYSTORE"
fi
apksigner sign --ks "$KEYSTORE" --ks-pass "pass:$STOREPASS" \
  --key-pass "pass:$STOREPASS" --out "$APK" "$APK_ALIGNED"

apksigner verify --print-certs "$APK" >/dev/null
echo
echo "built: $APK  ($(( $(stat -c%s "$APK") / 1024 )) KB)"
