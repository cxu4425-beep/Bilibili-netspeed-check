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
KEYSTORE=${KEYSTORE:-$OUT/debug.keystore}
STOREPASS=${STOREPASS:-lagscope}

for tool in aapt zipalign apksigner javac keytool; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done
[ -f "$PLATFORM" ] || { echo "missing android.jar: $PLATFORM" >&2; exit 1; }
[ -f tools/dx.jar ] || { echo "missing tools/dx.jar" >&2; exit 1; }

rm -rf "$OUT"; mkdir -p "$OUT/gen" "$OUT/classes"

echo "[1/6] aapt: resources + R.java"
aapt package -f -m \
  -J "$OUT/gen" -M AndroidManifest.xml -S res -I "$PLATFORM" \
  -F "$OUT/resources.ap_"

echo "[2/6] javac"
# Android's dex format predates newer class-file versions; 8 is what dx reads.
javac -source 8 -target 8 -nowarn -encoding UTF-8 \
  -bootclasspath "$PLATFORM" -classpath "$PLATFORM" \
  -d "$OUT/classes" \
  $(find src "$OUT/gen" -name '*.java') 2>&1 | grep -v "bootstrap class path" || true

echo "[3/6] dx: classes -> dex"
java -cp tools/dx.jar com.android.dx.command.Main --dex \
  --output="$OUT/classes.dex" "$OUT/classes"

echo "[4/6] package"
cp "$OUT/resources.ap_" "$APK_UNSIGNED"
( cd "$OUT" && aapt add -k "$(basename "$APK_UNSIGNED")" classes.dex >/dev/null )

echo "[5/6] zipalign"
# Alignment must happen before signing: v2 signatures cover the whole archive,
# so aligning afterwards would invalidate them.
zipalign -f 4 "$APK_UNSIGNED" "$APK_ALIGNED"

echo "[6/6] sign"
if [ ! -f "$KEYSTORE" ]; then
  # Self-signed, for sideloading. Keep this file: Android will refuse an
  # update signed by a different key, so a lost keystore means every user
  # has to uninstall before they can upgrade.
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
