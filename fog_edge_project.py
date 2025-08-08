import random
import time
import boto3
from datetime import datetime
import matplotlib.pyplot as plt
import os

# ==================================================
# AWS credentials (YOUR account details)
# ==================================================
ACCESS_KEY = 'AKIAUSJEUGSM56S2UUNU'
SECRET_KEY = 'NPHV1byDmR84ugNMPlA235+fiPm8xBEt+F6DZttw'
BUCKET_NAME = 'smart-home-data-2025'

# Initialize S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY
)

# Store readings for graph
temperature_history = []

# ==================================================
# EDGE LAYER - Simulated IoT Sensor
# ==================================================
def edge_generate_temperature():
    """Simulates a temperature reading from a sensor."""
    temp = round(random.uniform(20.0, 40.0), 2)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[EDGE] Sensor Reading: {temp}°C at {timestamp}")
    return temp, timestamp

# ==================================================
# FOG LAYER - Data Processing and Cloud Upload
# ==================================================
def fog_process_and_upload(temp, timestamp):
    """Processes sensor data and uploads to AWS S3 if above threshold."""
    temperature_history.append((timestamp, temp))

    if temp > 30:
        print("[FOG] High temperature detected! Preparing upload...")

        ts = int(time.time())
        filename_txt = f"temperature_{ts}.txt"
        filename_png = f"temperature_graph_{ts}.png"

        # Save reading to .txt file
        with open(filename_txt, "w") as file:
            file.write(f"Temperature: {temp}°C\nTime: {timestamp}")

        # Generate improved graph
        times = [t[0] for t in temperature_history]
        temps = [t[1] for t in temperature_history]
        colors = ['red' if t > 30 else 'green' for t in temps]

        plt.figure(figsize=(10, 6))
        plt.plot(times, temps, linestyle='-', color='blue', label='Temperature')
        plt.scatter(times, temps, c=colors, edgecolors='black', s=100)
        plt.axhline(y=30, color='orange', linestyle='--', linewidth=2, label='Threshold (30°C)')
        plt.title(f'Temperature Readings - {datetime.now().strftime("%Y-%m-%d")}', fontsize=16)
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Temperature (°C)', fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.legend()
        plt.savefig(filename_png)
        plt.close()

        # Upload files to S3
        try:
            s3.upload_file(filename_txt, BUCKET_NAME, filename_txt)
            s3.upload_file(filename_png, BUCKET_NAME, filename_png)
            print(f"[FOG] Uploaded {filename_txt} and {filename_png} to S3 ✅")
        except Exception as e:
            print(f"[FOG] Upload failed: {e}")

        # Remove local files to save space
        os.remove(filename_txt)
        os.remove(filename_png)

    else:
        print("[FOG] Temperature normal. No upload needed.")

# ==================================================
# MAIN LOOP - Runs forever
# ==================================================
while True:
    # EDGE: Generate reading
    temp, timestamp = edge_generate_temperature()

    # FOG: Process and upload if needed
    fog_process_and_upload(temp, timestamp)

    # Wait before next reading
    time.sleep(5)

