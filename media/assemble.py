#!/usr/bin/env python3
"""Assemble the GAFFER demo: static frames + smooth cross-dissolves (no shake),
Polly voiceover, burned caption PNGs. Computes xfade offsets so audio + captions
stay in sync on the dissolve timeline."""
import os, subprocess
FF = "/opt/homebrew/bin/ffmpeg"; FP = "/opt/homebrew/bin/ffprobe"
ROOT = "/Users/dhruvjain/gaffer/media"
SH, AU, BU, CA = f"{ROOT}/shots", f"{ROOT}/audio", f"{ROOT}/build", f"{ROOT}/build/caps"
os.makedirs(BU, exist_ok=True)
FPS = 30; PAD = 0.55; T = 0.6   # hold tail per scene, cross-dissolve length

def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG ERR:", " ".join(args)[:200]); print(r.stderr[-1500:]); raise SystemExit(1)

# narration durations
d = {}
for ln in open(f"{AU}/durations.txt"):
    i, v = ln.split(); d[int(i)] = float(v)

# segment list: (still, narration-scene). scene 8 spans two stills (browse+plan).
SEGS = [
    ("home", 1), ("home", 2), ("ask", 3), ("trace", 4), ("loop_trace", 5),
    ("loop_diff", 6), ("loop_scrim", 7), ("matches_browse", 8), ("matches_plan", 8),
    ("home", 9),
]
# hold per segment
hold = []
for still, sc in SEGS:
    if sc == 8:
        hold.append((d[8] + PAD) / 2.0)   # split scene-8 audio across its two stills
    else:
        hold.append(d[sc] + PAD)

# 1) build static segments (fast)
print("building static segments...")
for k, ((still, sc), h) in enumerate(zip(SEGS, hold), 1):
    out = f"{BU}/seg_{k:02d}.mp4"
    run([FF, "-y", "-loglevel", "error", "-loop", "1", "-t", f"{h:.3f}",
         "-i", f"{SH}/{still}.png", "-r", str(FPS),
         "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out])

# 2) xfade chain. O[k] = start time of seg k's dissolve on the growing chain.
O = [0.0]
for k in range(1, len(SEGS)):
    O.append(O[k-1] + hold[k-1] - T)
V = O[-1] + hold[-1]
print(f"total V = {V:.2f}s")

inputs = []
for k in range(len(SEGS)):
    inputs += ["-i", f"{BU}/seg_{k+1:02d}.mp4"]
fc = ""; prev = "0:v"
for k in range(1, len(SEGS)):
    out = f"x{k}"
    fc += f"[{prev}][{k}:v]xfade=transition=fade:duration={T}:offset={O[k]:.3f}[{out}];"
    prev = out
fc += f"[{prev}]format=yuv420p[vx]"
run([FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
     "-map", "[vx]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
     "-pix_fmt", "yuv420p", f"{BU}/video_x.mp4"])

# 3) per-narration start time A[sc] and caption window [cs, ce]
A = {}; capwin = {}
# first-seg index for each narration scene
firstseg = {}
for idx, (still, sc) in enumerate(SEGS):
    if sc not in firstseg:
        firstseg[sc] = idx
for sc in range(1, 10):
    fi = firstseg[sc]
    A[sc] = O[fi] + 0.12
    # scene end = start of next scene's first seg dissolve (or V)
    nextfi = firstseg.get(sc + 1)
    end = (O[nextfi] + T * 0.5) if nextfi is not None else V
    capwin[sc] = (O[fi] + 0.06, end - 0.04)

# 4) audio: silent bed of length V + each narration delayed to A[sc]
abuild = ["-f", "lavfi", "-t", f"{V:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
amix = "[0:a]"
for sc in range(1, 10):
    abuild += ["-i", f"{AU}/s{sc}.wav"]
fc_a = ""
for n, sc in enumerate(range(1, 10), start=1):
    ms = int(A[sc] * 1000)
    fc_a += f"[{n}:a]adelay={ms}|{ms}[a{n}];"
mixins = "".join(f"[a{n}]" for n in range(1, 10))
fc_a += f"[0:a]{mixins}amix=inputs=10:normalize=0:duration=longest[amx]"
run([FF, "-y", "-loglevel", "error", *abuild, "-filter_complex", fc_a,
     "-map", "[amx]", "-ar", "48000", "-ac", "2", f"{BU}/voice.wav"])

# 5) overlay caption PNGs (timed) + global fades + mux + loudnorm
inp = ["-i", f"{BU}/video_x.mp4"]
for sc in range(1, 10):
    inp += ["-i", f"{CA}/cap_{sc}.png"]
inp += ["-i", f"{BU}/voice.wav"]
fc2 = ""; prev = "0:v"
for n, sc in enumerate(range(1, 10), start=1):
    cs, ce = capwin[sc]
    out = f"c{n}"
    fc2 += f"[{prev}][{n}:v]overlay=0:0:enable='between(t,{cs:.3f},{ce:.3f})'[{out}];"
    prev = out
FO = V - 0.6
fc2 += f"[{prev}]fade=t=in:st=0:d=0.5,fade=t=out:st={FO:.3f}:d=0.6,format=yuv420p[v];"
fc2 += f"[10:a]afade=t=in:st=0:d=0.25,afade=t=out:st={FO:.3f}:d=0.6,loudnorm=I=-15:TP=-1.5:LRA=11[a]"
run([FF, "-y", "-loglevel", "error", *inp, "-filter_complex", fc2,
     "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
     "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
     f"{ROOT}/gaffer_demo.mp4"])
print("DONE ->", f"{ROOT}/gaffer_demo.mp4")
out = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", f"{ROOT}/gaffer_demo.mp4"], capture_output=True, text=True)
print("duration:", out.stdout.strip())
