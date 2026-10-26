#!/usr/bin/env python3
import csv, os, time

out = os.environ["OUT"]
status = os.environ.get("FAKE_STATUS", "OK")
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
print("model: sdk_gphone64_arm64")
print("qemu: 1")
print("plan: 1 rounds {'wipe': 1}")
print("=== round 1/1 (wipe) ===")
print("  cold boot with -wipe-data ...")
print("  android_id: before123 -> after456")
print("  click ok: True apk: https://x/a.apk")
print("  host download ok: 81587534 bytes")
print("  pm install ...")
print("    app tap: 同意")
print("  channel: wdb-ltt | status: " + status)
apk = os.environ.get("FAKE_APK")
if apk:
    with open(apk, "wb") as fh:
        fh.write(b"x" * 1024)
csv.writer(open(out, "w", newline="", encoding="utf-8")).writerow([
    "round", "reset", "android_id_before", "android_id_after", "public_ip",
    "clicked_at", "click_url", "apk_url", "install_at", "open_at", "installer",
    "first_install", "openinstall_channel", "app_version", "status",
    "log_excerpt", "apk_src"])
csv.writer(open(out, "a", newline="", encoding="utf-8")).writerow([
    1, "wipe", "before123", "after456", "1.2.3.4", "t1", "cu", "au", "t2", "t3",
    "null", "2026-10-26", "wdb-ltt", "2.7.1", status, "excerpt", "click"])