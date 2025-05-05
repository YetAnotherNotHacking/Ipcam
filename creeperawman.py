# https://silverflag.net/ (c) 2025
import cv2
import threading
import numpy as np
import random
import time
import requests
import urllib.parse
import logging
import os
import psutil
import pyautogui

logging.basicConfig(level=logging.DEBUG)

# If the camera needs special inputs, define it's endpoint here and supply the content including and following the '?'
default_stream_params = {
    "nphMotionJpeg": "?Resolution=640x480&Quality=Standard",
    "faststream.jpg": "?stream=full&fps=16",
    "SnapshotJPEG": "?Resolution=640x480&amp;Quality=Clarity&amp;1746245729",
    "cgi-bin/camera": "?resolution=640&amp;quality=1&amp;Language=0"
}

# Timing
start_time = time.time()

# The previous functions were not working correcty, later: update this to actually get the screen x and y
def get_screen_x():
    return 1920
def get_screen_y():
    return 1080
def get_cpu_usage():
    return psutil.cpu_percent(interval=1)
def is_jpg_poll_stream(url):
    return url.endswith('.jpg') or '.jpg?' in url or '.cgi' in url
def add_custom_params(url):
    parsed_url = urllib.parse.urlparse(url)
    path = parsed_url.path.lower()
    for key, param in default_stream_params.items():
        if key in path:
            if "?" in url:
                if not any(param.startswith(f"{x}=") for x in param.split("&")):
                    url += f"&{param.strip('?')}"
            else:
                url += f"?{param.strip('?')}"
            break
    return url
def read_stream(input_id, frames, borders, lock):
    try:
        def should_poll_jpeg(url):
            lower = url.lower()
            return any(p in lower for p in [
                "/cgi-bin/camera",
                "/snapshotjpeg",
                "/oneshotimage1",
                "/oneshotimage2",
                "/oneshotimage3",
                "/getoneshot",
                "/nphmotionjpeg",
                "/cam1ir",
                "/cam1color",
                "/image",
                ".jpg",
                ".jpeg"
            ])
        if input_id.startswith("rtsp://") or input_id.startswith("http://"):
            full_url = input_id
        elif any(x in input_id.lower() for x in [
            "/cam", "/cgi-bin", "/snapshotjpeg", "/oneshotimage", "/getoneshot", "/nphmotionjpeg",
            "/cam1ir", "/cam1color", ".jpg", ".jpeg", ".mjpg", ".mjpeg"
        ]):
            full_url = f"http://{input_id}" if not input_id.startswith("http") else input_id
        else:
            print(f"[{input_id}] Rejected: Invalid stream identifier")
            return
        full_url = add_custom_params(full_url)
        color = tuple(random.randint(64, 255) for _ in range(3))
        with lock:
            borders[input_id] = color
        if should_poll_jpeg(full_url):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            print(f"[{input_id}] Starting JPEG poll stream: {full_url}")
            while True:
                try:
                    req = urllib.request.Request(full_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        img_array = np.asarray(bytearray(resp.read()), dtype=np.uint8)
                        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if frame is not None:
                            with lock:
                                frames[input_id] = frame
                except Exception as e:
                    print(f"[{input_id}] JPEG poll error: {e}")
                time.sleep(0.1)
        else:
            print(f"[{input_id}] Opening stream with OpenCV: {full_url}")
            cap = cv2.VideoCapture(full_url)
            if not cap.isOpened():
                print(f"[{input_id}] Failed to open stream")
                return
            print(f"[{input_id}] Successfully opened stream")
            while True:
                ret, frame = cap.read()
                if not ret:
                    print(f"[{input_id}] Frame read failed, ending stream")
                    break
                with lock:
                    frames[input_id] = frame
                time.sleep(0.03)
            cap.release()
    except Exception as outer:
        print(f"[{input_id}] Fatal error: {outer}")
    finally:
        with lock:
            frames.pop(input_id, None)
            borders.pop(input_id, None)
        print(f"[{input_id}] Stream handler exiting")
# Protect the ego
def add_logo(full_grid):
    logo_path = "sf-logo-long-plain.webp"
    if not os.path.exists(logo_path):
        logo_url = "https://raw.githubusercontent.com/Silverflag/sf-clearnet-v2/refs/heads/main/assets/logos/sf-logo-long-plain.webp"
        logo = requests.get(logo_url).content
        with open(logo_path, 'wb') as f:
            f.write(logo)
    logo_img = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
    logo_height = 30
    logo_width = int(logo_img.shape[1] * (logo_height / logo_img.shape[0]))
    logo_resized = cv2.resize(logo_img, (logo_width, logo_height))
    if logo_resized.shape[2] == 4:
        logo_resized = cv2.cvtColor(logo_resized, cv2.COLOR_BGRA2BGR)
    full_grid[5:5 + logo_resized.shape[0], -logo_resized.shape[1] - 50:-50] = logo_resized
    return full_grid
def layout_frames(frames_dict, borders_dict, labels_dict):
    frames = list(frames_dict.items())
    count = len(frames)
    if count == 0:
        object = np.zeros((480, 640, 3), dtype=np.uint8)
        message_no_cameras = "No cameras have connected yet..."
        cv2.putText(object, message_no_cameras, (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        return object
    cols = int(np.ceil(np.sqrt(count)))
    rows = int(np.ceil(count / cols))
    screen_w, screen_h = get_screen_x(), get_screen_y()
    cell_w = screen_w // cols
    cell_h = screen_h // rows
    grid_rows = []
    for r in range(rows):
        row_imgs = []
        for c in range(cols):
            i = r * cols + c
            if i >= count:
                blank = np.zeros((cell_h, cell_w, 3), dtype=np.uint8)
                row_imgs.append(blank)
                continue
            url, frame = frames[i]
            original_height, original_width = frame.shape[:2]
            resolution_text = f"{original_width}x{original_height}"
            frame = cv2.resize(frame, (cell_w - 6, cell_h - 6))
            resized_height, resized_width = frame.shape[:2]
            label = labels_dict.get(url, url)
            cv2.rectangle(frame, (0, 0), (cell_w, 25), (0, 0, 0), -1)
            cv2.putText(frame, label, (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.rectangle(frame, (0, resized_height-25), (200, resized_height), (0, 0, 0), -1)
            cv2.putText(frame, resolution_text, (5, resized_height-7), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
            bordered = cv2.copyMakeBorder(frame, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=borders_dict.get(url, (0, 255, 0)))
            row_imgs.append(bordered)
        row = np.hstack(row_imgs)
        grid_rows.append(row)
    full_grid = np.vstack(grid_rows)
    full_grid = cv2.copyMakeBorder(full_grid, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(100, 100, 100))
    uptime = time.time() - start_time
    current_process_memory_usage = f"{psutil.Process().memory_info().rss / 1024 ** 2:.0f}MB / {psutil.virtual_memory().total / 1024 ** 2:.0f}MB"
    uptime_str = f"Uptime: {int(uptime // 60)} minutes and {int(uptime % 60)} seconds"
    camera_count = f"Connected Cameras: {len(frames_dict)}"
    displayed_cpu_usage = f"Host CPU: {get_cpu_usage()}"
    cv2.putText(full_grid, camera_count, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(full_grid, uptime_str, (460, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(full_grid, displayed_cpu_usage, (950, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(full_grid, current_process_memory_usage, (1240, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    final_full_grid = add_logo(full_grid)
    return final_full_grid
def main():
    with open("ip_list.txt") as f:
        inputs = [line.strip() for line in f if line.strip()]
    logging.debug(f"Loaded {len(inputs)} streams from ip_list.txt.")
    frames = {}
    borders = {}
    labels = {}
    lock = threading.Lock()
    for input_id in inputs:
        threading.Thread(target=read_stream, args=(input_id, frames, borders, lock), daemon=True).start()
    cv2.namedWindow("All Streams", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("All Streams", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    while True:
        with lock:
            grid = layout_frames(frames, borders, labels)
        cv2.imshow("All Streams", grid)
        if cv2.waitKey(1) == 27:
            break
    cv2.destroyAllWindows()
main()
# https://silverflag.net/ (c) 2025
