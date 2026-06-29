#!/bin/bash
set -e
FF=/opt/homebrew/bin/ffmpeg; FP=/opt/homebrew/bin/ffprobe
ROOT=/Users/dhruvjain/gaffer/media
SH=$ROOT/shots; AU=$ROOT/audio; BU=$ROOT/build
mkdir -p $BU; rm -f $BU/seg_*.mp4 $BU/*.ass $BU/*.txt
PAD=0.45   # trailing hold after each narration line
FPS=30

# scene -> still, zoom direction (in/out), caption (ASS markup, {g}=green keyword)
STILL=( home home ask trace loop_trace loop_diff loop_scrim matches_browse matches_plan home )
#        s1   s2   s3  s4    s5         s6       s7         s8a            s8b           s9
dur(){ awk -v i=$1 '$1==i{print $2}' $AU/durations.txt; }

GREEN='&H72b44f&'; WHITE='&H00ffffff&'
# ---- build ASS captions ----
A=$BU/caps.ass
cat > $A <<'HEAD'
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Helvetica Neue,54,&H00ffffff,&H00ffffff,&H00101410,&H00000000,-1,0,0,0,100,100,0.6,0,1,4,2,2,140,140,96,1
Style: Kick,Avenir Next,30,&H72b44f,&H72b44f,&H00101410,&H00000000,-1,0,0,0,100,100,3,0,1,3,0,2,140,140,176,1

[Events]
Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text
HEAD

# helper to emit a dialogue line spanning [start,end] seconds
ass_t(){ awk -v s=$1 'BEGIN{h=int(s/3600);m=int((s%3600)/60);sec=s-h*3600-m*60;printf "%d:%02d:%05.2f",h,m,sec}'; }
emit(){ # $1 start $2 end $3 text
  echo "Dialogue: 0,$(ass_t $1),$(ass_t $2),Cap,,0,0,0,,$3" >> $A; }
emitk(){ echo "Dialogue: 0,$(ass_t $1),$(ass_t $2),Kick,,0,0,0,,$3" >> $A; }

# captions (with green keyword via inline override)
declare -a CAP
CAP[1]="Most AI is {\\c$GREEN}confidently wrong{\\c$WHITE}"
CAP[2]="{\\c$GREEN}Everything{\\c$WHITE} for the World Cup.\\N{\\c$GREEN}Nothing{\\c$WHITE} made up."
CAP[3]="Every fact has a {\\c$GREEN}source{\\c$WHITE}"
CAP[4]="Traced live in {\\c$GREEN}Arize Phoenix{\\c$WHITE}"
CAP[5]="It {\\c$GREEN}referees itself{\\c$WHITE}"
CAP[6]="Coaches itself:  {\\c$GREEN}MISS  →  GOAL{\\c$WHITE}"
CAP[7]="Promoted only when {\\c$GREEN}data proves it{\\c$WHITE}"
CAP[8]="Plan the whole trip, {\\c$GREEN}grounded{\\c$WHITE}"
CAP[9]="{\\c$GREEN}GAFFER{\\c$WHITE}    Google ADK + Gemini    Arize Phoenix"

# ---- build segments + caption timing ----
ZDIR=( in in in in in in in in out )   # per audio-scene; scene8 split handled below
t=0
seg=0
make_seg(){ # $1 still  $2 dur  $3 zoomdir
  seg=$((seg+1)); local img=$SH/$1.png; local d=$2; local zd=$3
  local frames=$(awk -v d=$d -v f=$FPS 'BEGIN{printf "%d", d*f}')
  local zexpr
  # on-based zoom (no drift). gentle 1.00 -> 1.09 over the clip.
  if [ "$zd" = "out" ]; then zexpr="if(gt(1.09-0.00030*on,1.0),1.09-0.00030*on,1.0)"; else zexpr="min(1.001+0.00030*on,1.09)"; fi
  # downscaled buffer (2304x1296) keeps zoompan fast while still supersampling 1080p
  $FF -y -loglevel error -i "$img" \
    -filter_complex "[0:v]scale=2304:1296,setsar=1,zoompan=z='$zexpr':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=$frames:s=1920x1080:fps=$FPS,format=yuv420p[v]" \
    -map "[v]" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$BU/seg_$(printf %02d $seg).mp4"
}

for i in 1 2 3 4 5 6 7; do
  d=$(awk -v x=$(dur $i) -v p=$PAD 'BEGIN{print x+p}')
  make_seg ${STILL[$((i-1))]} $d ${ZDIR[$((i-1))]}
  emit $t $(awk -v a=$t -v b=$d 'BEGIN{print a+b}') "${CAP[$i]}"
  t=$(awk -v a=$t -v b=$d 'BEGIN{print a+b}')
done
# scene 8 split into two stills sharing one caption + one narration
d8=$(awk -v x=$(dur 8) -v p=$PAD 'BEGIN{print x+p}')
h8=$(awk -v d=$d8 'BEGIN{print d/2}')
make_seg matches_browse $h8 in
make_seg matches_plan $h8 in
emit $t $(awk -v a=$t -v b=$d8 'BEGIN{print a+b}') "${CAP[8]}"
t=$(awk -v a=$t -v b=$d8 'BEGIN{print a+b}')
# scene 9
d9=$(awk -v x=$(dur 9) -v p=$PAD 'BEGIN{print x+p}')
make_seg home $d9 out
emit $t $(awk -v a=$t -v b=$d9 'BEGIN{print a+b}') "${CAP[9]}"
TOTAL=$(awk -v a=$t -v b=$d9 'BEGIN{print a+b}')
echo "TOTAL video = $TOTAL s"

# ---- concat video segments ----
ls $BU/seg_*.mp4 | sort | sed "s/^/file '/;s/$/'/" > $BU/list.txt
$FF -y -loglevel error -f concat -safe 0 -i $BU/list.txt -c copy $BU/video_raw.mp4

# ---- build audio track: each narration + PAD silence ----
: > $BU/alist.txt
for i in 1 2 3 4 5 6 7 8 9; do
  $FF -y -loglevel error -i $AU/s$i.wav -af "apad=pad_dur=$PAD" -ar 48000 -ac 2 $BU/a$i.wav
  echo "file 'a$i.wav'" >> $BU/alist.txt
done
$FF -y -loglevel error -f concat -safe 0 -i $BU/alist.txt -c copy $BU/voice.wav

# ---- final: burn captions, mux audio, global fade in/out, loudness normalize ----
DUR=$($FP -v error -show_entries format=duration -of csv=p=0 $BU/video_raw.mp4)
FO=$(awk -v d=$DUR 'BEGIN{print d-0.6}')
$FF -y -loglevel error -i $BU/video_raw.mp4 -i $BU/voice.wav \
  -filter_complex "[0:v]subtitles=$BU/caps.ass:fontsdir=/System/Library/Fonts,fade=t=in:st=0:d=0.5,fade=t=out:st=$FO:d=0.6[v];[1:a]afade=t=in:st=0:d=0.3,afade=t=out:st=$FO:d=0.6,loudnorm=I=-16:TP=-1.5:LRA=11[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart \
  $ROOT/gaffer_demo.mp4
echo "=== DONE ==="; $FP -v error -show_entries format=duration:stream=width,height -of default=noprint_wrappers=1 $ROOT/gaffer_demo.mp4
ls -la $ROOT/gaffer_demo.mp4
