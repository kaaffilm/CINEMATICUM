#!/usr/bin/env python3
from pathlib import Path
import math, subprocess, json, hashlib, os, shutil

ROOT = Path.cwd()
SHOT_DIR = ROOT / "source/films/THE_LAST_RENDER/shots"
STILL_DIR = ROOT / "source/films/THE_LAST_RENDER/generated_stills"
OUT_DIR = ROOT / "dist/films/THE_LAST_RENDER"

SHOT_DIR.mkdir(parents=True, exist_ok=True)
STILL_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1280, 720
FPS = 24

shots = [
    ("001_threshold", 4.0, "threshold before entry", 82),
    ("002_approach", 7.0, "approach to sealed building", 96),
    ("003_refusal", 6.0, "door refuses the figure", 61),
    ("004_corridor", 7.0, "long interior corridor", 74),
    ("005_machine_room", 7.0, "rendering machine discovered", 49),
    ("006_switch", 5.0, "hand reaches the switch", 110),
    ("007_break", 6.0, "image system breaks", 137),
    ("008_aftercut", 5.0, "silence after rupture", 43),
    ("009_exit", 8.0, "exit into exterior light", 88),
    ("010_end", 4.0, "final locked frame", 57),
]

def clamp(v):
    return max(0, min(255, int(v)))

def bg(img, top, bot, noise=0):
    for y in range(H):
        k = y / max(1, H - 1)
        r = top[0] * (1-k) + bot[0] * k
        g = top[1] * (1-k) + bot[1] * k
        b = top[2] * (1-k) + bot[2] * k
        row = bytearray()
        for x in range(W):
            n = ((x * 17 + y * 31) % 29 - 14) * noise
            row.extend((clamp(r+n), clamp(g+n), clamp(b+n)))
        img[y] = row

def rect(img, x0, y0, x1, y1, c):
    x0, x1 = sorted((max(0,int(x0)), min(W,int(x1))))
    y0, y1 = sorted((max(0,int(y0)), min(H,int(y1))))
    pix = bytes(c)
    for y in range(y0, y1):
        row = img[y]
        for x in range(x0, x1):
            i = x * 3
            row[i:i+3] = pix

def circle(img, cx, cy, r, c):
    cx, cy, r = int(cx), int(cy), int(r)
    rr = r*r
    pix = bytes(c)
    for y in range(max(0, cy-r), min(H, cy+r)):
        row = img[y]
        dy = y - cy
        for x in range(max(0, cx-r), min(W, cx+r)):
            if (x-cx)*(x-cx) + dy*dy <= rr:
                i = x * 3
                row[i:i+3] = pix

def line(img, x0, y0, x1, y1, c, thick=3):
    steps = max(abs(int(x1-x0)), abs(int(y1-y0)), 1)
    for i in range(steps + 1):
        t = i / steps
        x = int(x0 + (x1-x0)*t)
        y = int(y0 + (y1-y0)*t)
        rect(img, x-thick, y-thick, x+thick, y+thick, c)

def figure(img, x, y, s=1.0, c=(8,8,9)):
    circle(img, x, y-78*s, 24*s, c)
    rect(img, x-20*s, y-55*s, x+20*s, y+50*s, c)
    line(img, x-18*s, y-25*s, x-55*s, y+35*s, c, int(6*s))
    line(img, x+18*s, y-25*s, x+55*s, y+35*s, c, int(6*s))
    line(img, x-12*s, y+45*s, x-35*s, y+105*s, c, int(8*s))
    line(img, x+12*s, y+45*s, x+35*s, y+105*s, c, int(8*s))

def write_ppm(path, img):
    with open(path, "wb") as f:
        f.write(f"P6\n{W} {H}\n255\n".encode())
        for row in img:
            f.write(row)

def make_still(idx, path):
    img = [bytearray(W*3) for _ in range(H)]

    if idx == 0:
        bg(img, (3,4,7), (18,18,22), 0.35)
        rect(img, 0, 500, W, H, (10,10,11))
        rect(img, 520, 180, 760, 570, (22,22,25))
        rect(img, 555, 215, 725, 570, (5,5,6))
        rect(img, 575, 235, 705, 550, (34,34,37))
        figure(img, 640, 540, 0.75)
    elif idx == 1:
        bg(img, (10,12,18), (50,48,44), 0.45)
        rect(img, 0, 530, W, H, (20,19,18))
        rect(img, 330, 160, 960, 540, (34,35,38))
        rect(img, 510, 240, 770, 540, (9,9,10))
        rect(img, 0, 0, W, 105, (6,7,10))
        figure(img, 350, 560, 0.65)
    elif idx == 2:
        bg(img, (4,5,8), (20,19,20), 0.25)
        rect(img, 355, 110, 925, 640, (25,25,28))
        rect(img, 430, 165, 850, 640, (7,7,8))
        rect(img, 815, 375, 835, 395, (180,155,80))
        rect(img, 420, 155, 860, 172, (90,82,65))
        figure(img, 640, 610, 0.72)
    elif idx == 3:
        bg(img, (7,8,10), (22,22,25), 0.2)
        for i in range(10):
            x = 90 + i*110
            rect(img, x, 110, x+38, 600, (30,30,33))
            rect(img, x+44, 160, x+82, 585, (10,10,11))
        line(img, 0, 620, W, 420, (60,60,62), 4)
        line(img, 0, 650, W, 500, (30,30,32), 5)
        figure(img, 500, 610, 0.55)
    elif idx == 4:
        bg(img, (5,6,8), (16,17,19), 0.2)
        rect(img, 140, 500, 1140, H, (9,9,10))
        rect(img, 455, 145, 825, 510, (42,43,46))
        rect(img, 500, 190, 780, 470, (6,7,9))
        for x in range(525, 760, 45):
            rect(img, x, 210, x+10, 450, (80,95,110))
        circle(img, 640, 330, 98, (18,28,38))
        circle(img, 640, 330, 52, (92,120,150))
        figure(img, 260, 575, 0.62)
    elif idx == 5:
        bg(img, (8,8,9), (24,22,20), 0.15)
        rect(img, 0, 500, W, H, (12,12,12))
        rect(img, 720, 180, 1030, 460, (28,28,30))
        circle(img, 875, 320, 52, (125,35,28))
        line(img, 270, 470, 840, 335, (12,12,12), 18)
        circle(img, 270, 470, 42, (18,18,18))
        rect(img, 832, 307, 918, 335, (160,42,32))
    elif idx == 6:
        bg(img, (10,3,4), (3,4,8), 0.7)
        for i in range(18):
            x = (i * 83) % W
            rect(img, x, 0, x+18, H, (120,20+i*5, 25))
        for i in range(9):
            line(img, 0, i*85, W, H-i*55, (190,190,170), 3)
        rect(img, 0, 0, W, 70, (240,230,200))
        rect(img, 0, 650, W, H, (2,2,2))
    elif idx == 7:
        bg(img, (2,3,4), (12,12,13), 0.05)
        rect(img, 0, 540, W, H, (7,7,8))
        rect(img, 545, 220, 735, 510, (13,13,14))
        rect(img, 575, 260, 705, 510, (3,3,3))
        circle(img, 642, 370, 28, (28,28,29))
    elif idx == 8:
        bg(img, (20,22,26), (90,83,70), 0.25)
        rect(img, 0, 520, W, H, (28,25,22))
        rect(img, 270, 170, 1010, 520, (45,42,38))
        rect(img, 610, 210, 860, 520, (150,135,100))
        rect(img, 660, 245, 815, 520, (215,195,145))
        figure(img, 930, 565, 0.52, (12,12,13))
    else:
        bg(img, (4,4,5), (7,7,8), 0.03)
        rect(img, 300, 150, 980, 560, (14,14,15))
        rect(img, 360, 210, 920, 500, (4,4,5))
        rect(img, 530, 250, 750, 500, (70,68,60))
        figure(img, 640, 560, 0.62)

    write_ppm(path, img)

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
if not ffmpeg or not ffprobe:
    raise SystemExit("FFMPEG_REQUIRED=true")

for i, (sid, dur, desc, freq) in enumerate(shots):
    still = STILL_DIR / f"{sid}.ppm"
    out = SHOT_DIR / f"{sid}.mp4"
    make_still(i, still)
    frames = int(round(dur * FPS))
    cmd = [
        ffmpeg, "-y",
        "-loop", "1", "-i", str(still),
        "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000",
        "-filter_complex",
        f"[0:v]zoompan=z='1+on*0.0007':x='iw/2-(iw/zoom/2)+sin(on/35)*28':y='ih/2-(ih/zoom/2)+cos(on/41)*18':d={frames}:s=854x480:fps={FPS},format=yuv420p[v];"
        f"[1:a]volume=0.05,afade=t=in:st=0:d=0.25,afade=t=out:st={max(0,dur-0.35)}:d=0.35[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", str(dur),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"SOURCE_SHOT_RENDERED={out}")

manifest = {
    "film": "THE_LAST_RENDER",
    "source_shot_generation": "GENERATED_VISUAL_SOURCE_SHOTS",
    "shot_count": len(shots),
    "fps": FPS,
    "shots": [
        {"id": sid, "duration_seconds": dur, "function": desc, "path": str(SHOT_DIR / f"{sid}.mp4")}
        for sid, dur, desc, freq in shots
    ],
}
manifest_path = OUT_DIR / "generated_source_shots_manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

print("SOURCE_SHOTS_READY=true")
print(f"SOURCE_SHOT_DIR={SHOT_DIR}")
print(f"SOURCE_SHOT_COUNT={len(shots)}")
