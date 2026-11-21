#!/bin/bash
# Compila o A95X Z2 Home sem Gradle: aapt2 -> # Requisitos (fora do projecto): JDK 17 + Android SDK (platforms;android-29, build-tools;34.0.0)
# em ~/android-build. A chave de assinatura fica em ~/android-build/keys (NUNCA no repositorio).
set -euo pipefail
cd "$(dirname "$0")"
AB=${ANDROID_BUILD:-$HOME/android-build}
export JAVA_HOME=$(ls -d "$AB"/jdk-17* | head -1)
export PATH=$JAVA_HOME/bin:$PATH
BT=$AB/sdk/build-tools/34.0.0
JAR=$AB/sdk/platforms/android-29/android.jar
KS=$AB/keys/a95x-launcher.jks
OUT=build
rm -rf $OUT && mkdir -p $OUT/res $OUT/classes $OUT/gen

if [ ! -f "$KS" ]; then
  mkdir -p "$(dirname "$KS")"
  pw=$(head -c 18 /dev/urandom | base64 | tr -d '/+=')
  echo "$pw" > "$AB/keys/a95x-launcher.pass"; chmod 600 "$AB/keys/a95x-launcher.pass"
  keytool -genkeypair -keystore "$KS" -storepass "$pw" -keypass "$pw" -alias a95x \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=A95X Z2 Home" >/dev/null 2>&1
fi
PW=$(cat "$AB/keys/a95x-launcher.pass")

$BT/aapt2 compile --dir res -o $OUT/res.zip
$BT/aapt2 link -o $OUT/unsigned.apk -I "$JAR" --manifest AndroidManifest.xml \
  $OUT/res.zip --min-sdk-version 24 --target-sdk-version 29
$BT/zipalign -f -p 4 $OUT/unsigned.apk $OUT/aligned.apk
$BT/apksigner sign --ks "$KS" --ks-pass "pass:$PW" --key-pass "pass:$PW" \
  --out A95XZ2-SettingsOverlay.apk $OUT/aligned.apk
$BT/apksigner verify A95XZ2-SettingsOverlay.apk && ls -la A95XZ2-SettingsOverlay.apk && sha256sum A95XZ2-SettingsOverlay.apk
