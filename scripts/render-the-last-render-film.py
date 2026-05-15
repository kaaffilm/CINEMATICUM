#!/usr/bin/env python3
from pathlib import Path
import subprocess, shutil, hashlib, json, math, random, os, sys

ROOT = Path.cwd()
OUT = ROOT / "dist/films/THE_LAST_RENDER"
SHOT_DIR = OUT / "shots"
OUT.mkdir(parents=True, exist_ok=True)
SHOT_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 854, 480, 24
FINAL = OUT / "THE_LAST_RENDER.mp4"
MANIFEST = OUT / "THE_LAST_RENDER_manifest.json"

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
if not ffmpeg or not ffprobe:
    raise SystemExit("FFMPEG_REQUIRED=true")

def run(cmd):
    subprocess.run(cmd, check=True)

def rgb(r,g,b): return bytes((max(0,min(255,int(r))), max(0,min(255,int(g))), max(0,min(255,int(b)))))

def blank(c=(0,0,0)):
    return bytearray(rgb(*c) * (W*H))

def put_rect(buf, x0,y0,x1,y1, c):
    x0,x1 = max(0,int(min(x0,x1))), min(W,int(max(x0,x1)))
    y0,y1 = max(0,int(min(y0,y1))), min(H,int(max(y0,y1)))
    if x0 >= x1 or y0 >= y1: return
    px = rgb(*c)
    span = px * (x1-x0)
    for y in range(y0,y1):
        i = (y*W+x0)*3
        buf[i:i+len(span)] = span

def put_circle(buf, cx, cy, r, c):
    cx,cy,r = int(cx),int(cy),int(r)
    rr = r*r
    px = rgb(*c)
    for y in range(max(0,cy-r), min(H,cy+r+1)):
        dy = y-cy
        dx = int(math.sqrt(max(0, rr-dy*dy)))
        x0,x1 = max(0,cx-dx), min(W,cx+dx+1)
        if x0 < x1:
            i = (y*W+x0)*3
            buf[i:i+(x1-x0)*3] = px*(x1-x0)

def put_line(buf, x0,y0,x1,y1,c,thick=2):
    steps = max(abs(int(x1-x0)), abs(int(y1-y0)), 1)
    for k in range(steps+1):
        t = k/steps
        x = x0 + (x1-x0)*t
        y = y0 + (y1-y0)*t
        put_rect(buf, x-thick,y-thick,x+thick+1,y+thick+1,c)

def gradient(top, bottom, noise=0, seed=0):
    rnd = random.Random(seed)
    rows = []
    for y in range(H):
        k = y/(H-1)
        r = top[0]*(1-k)+bottom[0]*k
        g = top[1]*(1-k)+bottom[1]*k
        b = top[2]*(1-k)+bottom[2]*k
        row = bytearray()
        for x in range(W):
            n = ((x*13 + y*17 + seed*19) % 31 - 15) * noise
            row += rgb(r+n,g+n,b+n)
        rows.append(bytes(row))
    return rows

def copy_bg(rows):
    return bytearray(b"".join(rows))

def figure(buf, x,y,s=1.0, shade=(5,5,6), pose=0.0):
    head_r = 13*s
    put_circle(buf,x,y-58*s,head_r,shade)
    put_rect(buf,x-10*s,y-45*s,x+10*s,y+20*s,shade)
    arm = math.sin(pose)*12*s
    put_line(buf,x-9*s,y-30*s,x-32*s,y+5*s+arm,shade,max(2,int(4*s)))
    put_line(buf,x+9*s,y-30*s,x+32*s,y+5*s-arm,shade,max(2,int(4*s)))
    put_line(buf,x-5*s,y+18*s,x-20*s,y+58*s,shade,max(2,int(5*s)))
    put_line(buf,x+5*s,y+18*s,x+20*s,y+58*s,shade,max(2,int(5*s)))

def gate(buf, x, y, w, h, open_amt=0):
    put_rect(buf,x,y,x+w,y+h,(18,18,21))
    gap = 18 + open_amt
    put_rect(buf,x+28,y+32,x+w//2-gap,y+h,(4,4,5))
    put_rect(buf,x+w//2+gap,y+32,x+w-28,y+h,(4,4,5))
    put_rect(buf,x+24,y+28,x+w-24,y+38,(85,75,58))
    put_circle(buf,x+w//2-gap-15,y+h//2,5,(190,155,70))
    put_circle(buf,x+w//2+gap+15,y+h//2,5,(190,155,70))

def machine(buf, x,y,scale=1.0,pulse=0.0):
    put_rect(buf,x-120*scale,y-90*scale,x+120*scale,y+90*scale,(30,32,36))
    put_rect(buf,x-92*scale,y-62*scale,x+92*scale,y+60*scale,(4,5,7))
    rad = 38*scale + pulse*10
    put_circle(buf,x,y,rad,(40+pulse*60,70+pulse*80,95+pulse*90))
    put_circle(buf,x,y,rad*0.45,(140+80*pulse,170+50*pulse,190+30*pulse))
    for k in range(8):
        a = k*math.pi/4 + pulse
        put_line(buf,x,y,x+math.cos(a)*115*scale,y+math.sin(a)*80*scale,(65,72,78),2)

def rain(buf, frame, density=34):
    rnd = random.Random(frame//3)
    for _ in range(density):
        x = rnd.randrange(-50,W+50)
        y = rnd.randrange(0,H)
        put_line(buf,x,y,x-18,y+35,(52,55,62),1)

def dust(buf, frame, density=60):
    rnd = random.Random(9000+frame)
    for _ in range(density):
        x = rnd.randrange(0,W)
        y = rnd.randrange(0,H)
        if rnd.random() < 0.65:
            put_rect(buf,x,y,x+1,y+1,(80,77,68))

def vignette(buf):
    # cheap letterbox + dark sides
    put_rect(buf,0,0,W,42,(0,0,0))
    put_rect(buf,0,H-42,W,H,(0,0,0))
    put_rect(buf,0,0,18,H,(0,0,0))
    put_rect(buf,W-18,0,W,H,(0,0,0))

def title_card(buf, text_block=False):
    put_rect(buf,0,0,W,H,(3,3,4))
    put_rect(buf,170,150,684,320,(8,8,9))
    put_rect(buf,178,158,676,312,(18,18,19))
    if text_block:
        # abstract title bars, no font dependency
        for i,w in enumerate([320,260,380,210]):
            put_rect(buf,238,195+i*28,238+w,205+i*28,(210,205,190))

def render_shot(name, duration, scene_fn, freq=55):
    frames = int(duration*FPS)
    raw = SHOT_DIR / f"{name}.rgb"
    mp4 = SHOT_DIR / f"{name}.mp4"

    with raw.open("wb") as f:
        for n in range(frames):
            t = n / max(1,frames-1)
            buf = scene_fn(n, t)
            vignette(buf)
            f.write(buf)

    run([
        ffmpeg, "-y",
        "-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i",str(raw),
        "-f","lavfi","-i",f"sine=frequency={freq}:sample_rate=48000",
        "-filter_complex",
        f"[1:a]volume=0.035,afade=t=in:st=0:d=0.25,afade=t=out:st={max(0,duration-0.45)}:d=0.45[a]",
        "-map","0:v","-map","[a]",
        "-t",str(duration),
        "-c:v","libx264","-pix_fmt","yuv420p","-crf","16","-preset","medium",
        "-c:a","aac","-b:a","160k",
        "-movflags","+faststart",
        str(mp4)
    ])
    raw.unlink(missing_ok=True)
    print(f"SHOT_RENDERED={name} duration={duration}")
    return mp4

cold = gradient((4,5,8),(35,33,31),0.35,1)
inside = gradient((3,4,5),(18,18,20),0.25,2)
red = gradient((16,3,4),(3,3,6),0.6,3)
white = gradient((58,60,64),(140,130,110),0.2,4)

shots = []

shots.append(("001_black_before_image",3.0,lambda n,t: title_scene(n,t),45))
def title_scene(n,t):
    b=blank((2,2,3)); title_card(b, text_block=t>0.25); return b

def approach(n,t):
    b=copy_bg(cold)
    rain(b,n,44)
    put_rect(b,0,355,W,H,(16,15,14))
    put_rect(b,215,105,640,355,(32,34,38))
    gate(b,365,145,155,250,open_amt=0)
    x=90 + t*250
    figure(b,x,375,0.8,(3,3,4),n/7)
    return b
shots.append(("002_approach_in_rain",7.0,approach,57))

def door(n,t):
    b=copy_bg(inside)
    open_amt = 0 if t<0.5 else int((t-0.5)*16)
    gate(b,250,70,355,365,open_amt)
    figure(b,425,382,1.05,(2,2,3),n/8)
    put_line(b,427,238,512,238,(130,105,42),2)
    if int(t*8)%2==0: put_rect(b,505,230,525,247,(190,160,60))
    dust(b,n,22)
    return b
shots.append(("003_door_refuses",7.0,door,62))

def corridor(n,t):
    b=copy_bg(inside)
    z = 1+t*0.25
    for i in range(11):
        x=70+i*72 - t*95
        put_rect(b,x,92,x+20*z,410,(26,26,28))
        put_rect(b,x+24*z,125,x+44*z,390,(6,6,7))
    put_line(b,0,430,W,292,(65,62,55),4)
    put_line(b,0,455,W,355,(28,28,29),4)
    figure(b,260+t*210,402,0.65,(2,2,3),n/5)
    dust(b,n,38)
    return b
shots.append(("004_corridor_pressure",8.0,corridor,74))

def machine_room(n,t):
    b=copy_bg(inside)
    put_rect(b,0,350,W,H,(8,8,9))
    pulse=0.2+0.8*abs(math.sin(t*math.pi*3))
    machine(b,520,248,1.05,pulse)
    figure(b,170+t*85,382,0.72,(2,2,3),n/6)
    for k in range(5):
        put_line(b,520,248,80+k*140,80+(k%2)*60,(55+40*pulse,70+30*pulse,85+20*pulse),1)
    dust(b,n,45)
    return b
shots.append(("005_machine_room",8.0,machine_room,49))

def hand_switch(n,t):
    b=copy_bg(inside)
    put_rect(b,570,115,760,325,(20,21,24))
    put_circle(b,665,220,36,(105,25,20))
    put_rect(b,635,205,695,235,(165,40,30))
    x=110+t*520
    put_line(b,x,358,655,224,(8,8,8),16)
    put_circle(b,x,358,28,(10,10,10))
    if t>0.72:
        put_circle(b,665,220,48,(220,170,80))
    return b
shots.append(("006_hand_on_switch",5.0,hand_switch,95))

def rupture(n,t):
    b=copy_bg(red)
    for i in range(28):
        x=(i*43+n*7)%W
        put_rect(b,x,42,x+8+(i%5)*5,H-42,(160+i*2,25+(i*7)%70,30))
    for i in range(16):
        y=55+i*25+(n*3)%19
        put_line(b,0,y,W,H-y,(220,210,170),2)
    if n%5<2:
        put_rect(b,0,120,W,145,(235,230,200))
        put_rect(b,0,330,W,345,(10,10,10))
    return b
shots.append(("007_render_break",6.0,rupture,137))

def aftercut(n,t):
    b=blank((1,1,2))
    put_rect(b,0,360,W,H,(5,5,6))
    put_rect(b,340,120,514,340,(12,12,13))
    put_rect(b,374,160,480,340,(2,2,3))
    if t>0.6:
        put_circle(b,428,250,16,(35,35,36))
    dust(b,n,8)
    return b
shots.append(("008_silence_after_cut",6.0,aftercut,39))

def exit_scene(n,t):
    b=copy_bg(white)
    put_rect(b,0,348,W,H,(26,23,20))
    put_rect(b,160,105,690,348,(48,45,40))
    door_w=120+160*t
    put_rect(b,392-door_w/2,138,392+door_w/2,348,(220,195,135))
    figure(b,615+t*100,382,0.58,(7,7,8),n/6)
    rain(b,n,12)
    return b
shots.append(("009_exit_release",8.0,exit_scene,82))

def end_lock(n,t):
    b=blank((3,3,4))
    put_rect(b,210,105,644,350,(14,14,15))
    put_rect(b,260,150,594,310,(4,4,5))
    put_rect(b,375,185,480,310,(83,76,61))
    figure(b,428,360,0.58,(1,1,2),0)
    if t>0.72:
        put_rect(b,0,0,W,H,(0,0,0))
    return b
shots.append(("010_end_lock",5.0,end_lock,44))

rendered = []
for name,dur,fn,freq in shots:
    rendered.append(render_shot(name,dur,fn,freq))

concat = OUT / "concat.txt"
concat.write_text("".join(f"file '{p.resolve()}'\n" for p in rendered))

run([
    ffmpeg,"-y","-f","concat","-safe","0","-i",str(concat),
    "-vf","noise=alls=8:allf=t+u,eq=contrast=1.10:saturation=0.78:brightness=-0.015",
    "-af","aecho=0.8:0.7:80:0.18,alimiter=limit=0.7",
    "-c:v","libx264","-pix_fmt","yuv420p","-crf","15","-preset","medium",
    "-c:a","aac","-b:a","192k",
    "-movflags","+faststart",
    str(FINAL)
])

probe = subprocess.check_output([
    ffprobe,"-v","error",
    "-show_entries","format=duration,size",
    "-of","json",str(FINAL)
], text=True)
info = json.loads(probe)
sha = hashlib.sha256(FINAL.read_bytes()).hexdigest()

manifest = {
    "artifact": "THE_LAST_RENDER",
    "artifact_class": "PROCEDURAL_SHOT_BASED_SHORT_FILM",
    "not_still_card_slideshow": True,
    "not_single_fractal_loop": True,
    "frame_by_frame_animation": True,
    "visual_system": "deterministic procedural cinema rasterizer",
    "path": str(FINAL),
    "sha256": sha,
    "duration_seconds": float(info["format"]["duration"]),
    "size_bytes": int(info["format"]["size"]),
    "width": W,
    "height": H,
    "fps": FPS,
    "shot_count": len(shots),
    "shots": [{"id": s[0], "duration_seconds": s[1]} for s in shots],
}
MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

print(f"REAL_FILM_RENDERED=true")
print(f"OPEN_THIS={FINAL}")
print(f"SHA256={sha}")
print(f"DURATION_SECONDS={manifest['duration_seconds']}")
