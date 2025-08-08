import random
import time
import os
from datetime import datetime
import boto3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates  # for nice time axis

# =========================
# AWS CONFIG
# =========================
ACCESS_KEY = 'AKIAUSJEUGSM56S2UUNU'
SECRET_KEY = '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'
BUCKET_NAME = 'smart-home-data-2025'
AWS_REGION = 'eu-west-1'  # Ireland
SNS_TOPIC_ARN = "arn:aws:sns:eu-west-1:314146305177:high-temp-alerts"

# =========================
# AWS CLIENTS
# =========================
s3 = boto3.client(
    's3',
    region_name=AWS_REGION,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY
)
sns = boto3.client(
    'sns',
    region_name=AWS_REGION,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY
)

# =========================
# EDGE/FOG SETTINGS
# =========================
THRESHOLD = 30.0
READ_INTERVAL_SEC = 5
ALERT_COOLDOWN_SEC = 60
last_alert_ts = 0

# Keep history of (datetime_obj, temp)
temperature_history = []

# -------------------------
# Helpers
# -------------------------
def rolling_mean(values, window):
    if window <= 1:
        return values[:]
    out = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        segment = values[start:i+1]
        out.append(sum(segment) / len(segment))
    return out

# =========================
# EDGE LAYER — Simulated IoT sensor
# =========================
def edge_generate_temperature():
    """Simulate a temperature reading from a sensor on the edge device."""
    temp = round(random.uniform(20.0, 40.0), 2)
    now_dt = datetime.now()
    ts_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[EDGE] Sensor Reading: {temp}°C at {ts_str}")
    return temp, ts_str, now_dt

# =========================
# FOG LAYER — Local processing, upload, alert
# =========================
def fog_process_and_upload(temp, ts_str, ts_dt):
    """Process locally at the fog layer; upload + alert only when needed."""
    global last_alert_ts
    temperature_history.append((ts_dt, temp))

    if temp > THRESHOLD:
        print("[FOG] High temperature detected! Preparing upload...")

        ts = int(time.time())
        filename_txt = f"temperature_{ts}.txt"
        filename_png = f"temperature_graph_{ts}.png"

        # 1) Save TXT summary
        with open(filename_txt, "w") as file:
            file.write(
                f"Temperature: {temp}°C\n"
                f"Time: {ts_str}\n"
                f"Threshold: {THRESHOLD}°C\n"
            )

        # 2) Create a clean, professional graph
        times = [t[0] for t in temperature_history]  # datetime objects
        temps = [t[1] for t in temperature_history]
        colors = ['red' if t > THRESHOLD else 'green' for t in temps]

        # Rolling average (smooth) over last ~6 points
        smooth = rolling_mean(temps, window=6)

        plt.figure(figsize=(11, 6.5))

        # Shade the region above threshold for clarity
        ax = plt.gca()
        ax.axhline(y=THRESHOLD, color='orange', linestyle='--', linewidth=2, label=f'Threshold ({THRESHOLD}°C)')
        ax.fill_between(times, THRESHOLD, max(max(temps)+2, THRESHOLD+2),
                        where=[True]*len(times), color='orange', alpha=0.08)

        # Main line + rolling average + scatter
        ax.plot(times, temps, linestyle='-', color='royalblue', linewidth=2, label='Temperature')
        ax.plot(times, smooth, linestyle='-', color='purple', linewidth=2, alpha=0.8, label='Rolling Avg')

        sc = ax.scatter(times, temps, c=colors, edgecolors='black', s=90, zorder=3)

        # Highlight last point with annotation
        last_t, last_v = times[-1], temps[-1]
        ax.scatter([last_t], [last_v], s=180, edgecolors='black', facecolors='yellow', zorder=4)
        ax.annotate(f"{last_v}°C",
                    (mdates.date2num(last_t), last_v),
                    textcoords="offset points",
                    xytext=(8, 8),
                    ha='left', fontsize=10,
                    bbox=dict(boxstyle="round,pad=0.2", fc="w", ec="gray", alpha=0.8))

        # Axis formatting
        ax.set_title(f"Smart Temperature Monitor — {datetime.now().strftime('%Y-%m-%d')}", fontsize=17, pad=12)
        ax.set_xlabel('Time', fontsize=12)
        ax.set_ylabel('Temperature (°C)', fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.5)

        # Nicely formatted time axis
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        plt.setp(ax.get_xticklabels(), rotation=30, ha='right')

        # Y-limits with a bit of padding
        ymin = min(temps) - 2
        ymax = max(temps) + 2
        ax.set_ylim(ymin, ymax)

        # Subtitle-like text with basic stats
        try:
            curr = temps[-1]
            tmax = max(temps)
            tmin = min(temps)
            ax.text(0.01, 0.98,
                    f"Current: {curr}°C   Max: {tmax}°C   Min: {tmin}°C",
                    transform=ax.transAxes, va='top', ha='left',
                    fontsize=11, color='dimgray')
        except Exception:
            pass

        ax.legend(loc='upper left')
        plt.tight_layout()
        plt.savefig(filename_png, dpi=150)
        plt.close()

        # 3) Upload files to S3
        try:
            s3.upload_file(filename_txt, BUCKET_NAME, filename_txt)
            s3.upload_file(filename_png, BUCKET_NAME, filename_png)
            print(f"[FOG] Uploaded {filename_txt} and {filename_png} to S3 ✅")
        except Exception as e:
            print(f"[FOG] Upload failed: {e}")

        # 4) SNS alert (cooldown)
        try:
            now = time.time()
            if now - last_alert_ts >= ALERT_COOLDOWN_SEC:
                now_iso = datetime.utcnow().isoformat()
                message = (
                    "⚠️ High temperature detected\n"
                    f"Temperature: {temp}°C\n"
                    f"Time (UTC): {now_iso}\n"
                    f"Bucket: {BUCKET_NAME}\n"
                    f"Files: {filename_txt}, {filename_png}"
                )
                sns.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Subject="High temperature alert (Edge/Fog demo)",
                    Message=message
                )
                last_alert_ts = now
                print("[FOG] SNS alert sent ✅")
            else:
                print("[FOG] Skipped SNS (cooldown active)")
        except Exception as e:
            print(f"[FOG] SNS publish failed: {e}")

        # 5) Cleanup local files
        try:
            os.remove(filename_txt)
            os.remove(filename_png)
            print("[FOG] Cleaned up local files 🧹")
        except Exception as e:
            print(f"[FOG] Cleanup warning: {e}")

    else:
        print("[FOG] Temperature normal. No upload needed.")

# =========================
# MAIN LOOP
# =========================
if __name__ == "__main__":
    try:
        while True:
            temp, ts_str, ts_dt = edge_generate_temperature()
            fog_process_and_upload(temp, ts_str, ts_dt)
            time.sleep(READ_INTERVAL_SEC)
    except KeyboardInterrupt:
        print("\n🛑 Script stopped by user. Goodbye!")

