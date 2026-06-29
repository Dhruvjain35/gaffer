#!/bin/bash
set -e
FF=/opt/homebrew/bin/ffmpeg; FP=/opt/homebrew/bin/ffprobe
ROOT=/Users/dhruvjain/gaffer/media; BU=$ROOT/build; CA=$BU/caps
DUR=$($FP -v error -show_entries format=duration -of csv=p=0 $BU/video_raw.mp4)
FO=$(awk -v d=$DUR 'BEGIN{printf "%.3f", d-0.6}')

# build inputs: video, 9 caption pngs, voice
INP="-i $BU/video_raw.mp4"
for i in 1 2 3 4 5 6 7 8 9; do INP="$INP -i $CA/cap_$i.png"; done
INP="$INP -i $BU/voice.wav"

# overlay chain from windows.txt
FC=""; prev="0:v"; idx=1
while read i s e; do
  out="v$idx"
  FC="$FC[$prev][$idx:v]overlay=0:0:enable='between(t,$s,$e)'[$out];"
  prev="$out"; idx=$((idx+1))
done < $CA/windows.txt
FC="$FC[$prev]fade=t=in:st=0:d=0.5,fade=t=out:st=$FO:d=0.6,format=yuv420p[v];"
FC="$FC[10:a]afade=t=in:st=0:d=0.3,afade=t=out:st=$FO:d=0.6,loudnorm=I=-16:TP=-1.5:LRA=11[a]"

$FF -y -loglevel error $INP -filter_complex "$FC" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart $ROOT/gaffer_demo.mp4

echo "=== DONE ==="
$FP -v error -show_entries format=duration:stream=width,height,codec_name -of default=noprint_wrappers=1 $ROOT/gaffer_demo.mp4
ls -lh $ROOT/gaffer_demo.mp4
