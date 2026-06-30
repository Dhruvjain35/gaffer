#!/bin/bash
# Regenerate narration with AWS Polly generative engine (premium, natural).
set -e
FF=/opt/homebrew/bin/ffmpeg; FP=/opt/homebrew/bin/ffprobe
AU=/Users/dhruvjain/gaffer/media/audio
VOICE="${POLLY_VOICE:-Matthew}"   # swap: Ruth / Stephen / Brian(en-GB) / Amy(en-GB)
ENGINE="${POLLY_ENGINE:-generative}"
cd $AU
declare -a N
N[1]="Watch an A.I. catch its own lie. A confident answer comes out. Its own referee stamps it false. And it corrects itself, on the spot, in seconds. Most A.I. cannot do that. This one was built to."
N[2]="This is Gaffer. It referees every single answer it gives, goal or miss, and writes the verdict live into Arize Phoenix. Nothing reaches you ungraded."
N[3]="When it misses, it coaches itself. It rewrites its own playbook, runs a paired Phoenix experiment, and only ships the change when the data proves it is actually better."
N[4]="Then we did the thing almost no one does. We graded the grader. We wrote twenty-two fabrications and tried to fool the referee. It caught all twenty-two, including the subtle ones."
N[5]="And every decision is auditable. Twenty-one scrimmage rounds, every promotion and every refusal it made, traced end to end in Arize Phoenix."
N[6]="The use case it runs on is the World Cup. A concierge that answers only from verified records, and flat out refuses to bluff."
N[7]="Ask it the messy, specific stuff, the rail route to the gate, the bag rules, the fare, and it grounds every fact, or tells you honestly when it cannot."
N[8]="Gaffer. The agent that catches and fixes its own lies. Built on Google's Agent Development Kit and Gemini. Kept honest by Arize Phoenix."
: > durations.txt
for i in $(seq 1 8); do
  aws polly synthesize-speech --engine "$ENGINE" --voice-id "$VOICE" \
    --output-format mp3 --text "${N[$i]}" "s$i.mp3" >/dev/null
  $FF -y -loglevel error -i "s$i.mp3" -ar 48000 -ac 2 "s$i.wav"
  d=$($FP -v error -show_entries format=duration -of csv=p=0 "s$i.wav")
  echo "$i $d" | tee -a durations.txt
done
echo "=== total ==="; awk '{s+=$2} END{print s" sec ('"$VOICE"'/'"$ENGINE"')"}' durations.txt