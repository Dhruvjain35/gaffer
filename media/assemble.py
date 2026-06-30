#!/usr/bin/env python3
"""Assemble the GAFFER demo: static frames + smooth cross-dissolves (no shake),
Polly voiceover, burned caption PNGs. Re-led to open on the self-correction hook.
One still + one caption + one narration per scene; xfade offsets keep A/V in sync."""
import os, subprocess
FF = "/opt/homebrew/bin/ffmpeg"; FP = "/opt/homebrew/bin/ffprobe"
ROOT = "/Users/dhruvjain/gaffer/media"
SH, AU, BU, CA = f"{ROOT}/shots", f"{ROOT}/audio", f"{ROOT}/build", f"{ROOT}/build/caps"
os.makedirs(BU, exist_ok=True)
FPS = 30; PAD = 0.55; T = 0.6   # hold tail per scene, cross-dissolve length

# one still per scene, re-led with the hook (catch its own lie) first
STILLS = ["stress", "trace", "loop_diff", "reportcard", "scoreboard", "matches_plan", "ask", "home"]
N = len(STILLS)

def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG ERR:", " ".join(args)[:160]); print(r.stderr[-1500:]); raise SystemExit(1)

d = {}
for ln in open(f"{AU}/durations.txt"):
    i, v = ln.split(); d[int(i)] = float(v)
hold = [d[i + 1] + PAD for i in range(N)]

# 1) static segments
print("building static segments...")
for k in range(N):
    run([FF, "-y", "-loglevel", "error", "-loop", "1", "-t", f"{hold[k]:.3f}",
         "-i", f"{SH}/{STILLS[k]}.png", "-r", str(FPS),
         "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         f"{BU}/seg_{k+1:02d}.mp4"])

# 2) xfade chain; O[k] = start of seg k's dissolve on the growing chain
O = [0.0]
for k in range(1, N):
    O.append(O[k - 1] + hold[k - 1] - T)
V = O[-1] + hold[-1]
print(f"total V = {V:.2f}s")
inputs = []
for k in range(N):
    inputs += ["-i", f"{BU}/seg_{k+1:02d}.mp4"]
fc = ""; prev = "0:v"
for k in range(1, N):
    fc += f"[{prev}][{k}:v]xfade=transition=fade:duration={T}:offset={O[k]:.3f}[x{k}];"; prev = f"x{k}"
fc += f"[{prev}]format=yuv420p[vx]"
run([FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", "[vx]",
     "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", f"{BU}/video_x.mp4"])

# 3) per-scene narration start + caption window
A = [O[k] + 0.12 for k in range(N)]
capwin = []
for k in range(N):
    end = (O[k + 1] + T * 0.5) if k + 1 < N else V
    capwin.append((O[k] + 0.06, end - 0.04))

# 4) audio: silent bed of length V + each narration delayed to A[k]
abuild = ["-f", "lavfi", "-t", f"{V:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
for k in range(N):
    abuild += ["-i", f"{AU}/s{k+1}.wav"]
fc_a = "".join(f"[{k+1}:a]adelay={int(A[k]*1000)}|{int(A[k]*1000)}[a{k+1}];" for k in range(N))
fc_a += "[0:a]" + "".join(f"[a{k+1}]" for k in range(N)) + f"amix=inputs={N+1}:normalize=0:duration=longest[amx]"
run([FF, "-y", "-loglevel", "error", *abuild, "-filter_complex", fc_a, "-map", "[amx]",
     "-ar", "48000", "-ac", "2", f"{BU}/voice.wav"])

# 5) overlay caption PNGs (timed) + global fades + mux + loudnorm
inp = ["-i", f"{BU}/video_x.mp4"]
for k in range(N):
    inp += ["-i", f"{CA}/cap_{k+1}.png"]
inp += ["-i", f"{BU}/voice.wav"]
voice_idx = N + 1
fc2 = ""; prev = "0:v"
for k in range(N):
    cs, ce = capwin[k]
    fc2 += f"[{prev}][{k+1}:v]overlay=0:0:enable='between(t,{cs:.3f},{ce:.3f})'[c{k+1}];"; prev = f"c{k+1}"
FO = V - 0.6
fc2 += f"[{prev}]fade=t=in:st=0:d=0.5,fade=t=out:st={FO:.3f}:d=0.6,format=yuv420p[v];"
fc2 += f"[{voice_idx}:a]afade=t=in:st=0:d=0.25,afade=t=out:st={FO:.3f}:d=0.6,loudnorm=I=-15:TP=-1.5:LRA=11[a]"
run([FF, "-y", "-loglevel", "error", *inp, "-filter_complex", fc2, "-map", "[v]", "-map", "[a]",
     "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
     "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", f"{ROOT}/gaffer_demo.mp4"])
print("DONE ->", f"{ROOT}/gaffer_demo.mp4")
out = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                      f"{ROOT}/gaffer_demo.mp4"], capture_output=True, text=True)
print("duration:", out.stdout.strip())
