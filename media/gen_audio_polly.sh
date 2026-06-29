#!/bin/bash
# Regenerate narration with AWS Polly generative engine (premium, natural).
set -e
FF=/opt/homebrew/bin/ffmpeg; FP=/opt/homebrew/bin/ffprobe
AU=/Users/dhruvjain/gaffer/media/audio
VOICE="${POLLY_VOICE:-Matthew}"   # swap: Ruth / Stephen / Brian(en-GB) / Amy(en-GB)
ENGINE="${POLLY_ENGINE:-generative}"
cd $AU
declare -a N
N[1]="Any chatbot can tell you who is playing. But ask the questions that actually decide your trip. Can I get through security with this. Which exact train reaches the gate. A normal AI just guesses, sounds certain, and you find out at the turnstile."
N[2]="Gaffer is built for exactly those questions. A World Cup concierge that answers only from verified records, and flat out refuses to bluff. Everything for the tournament. Nothing made up."
N[3]="Ask it the messy, specific stuff. The matchday rail route, the bag and re-entry rules, the fare and the rider cap. Gaffer pulls every detail from its knowledge base, and shows the source behind each one."
N[4]="And every answer is traced, live, inside Arize Phoenix. One click opens the full reasoning trail, so you can audit exactly where each fact came from."
N[5]="Here is what makes it trustworthy. Gaffer referees itself. An AI judge grades every answer, goal or miss, and writes the verdict straight back into Phoenix."
N[6]="And when an answer misses, the coach rewrites Gaffer's own prompt, and tries again on the spot. From miss, to goal, correcting itself in real time."
N[7]="This isn't guesswork. Every new prompt is tested in paired Phoenix experiments, and only goes live when the data proves it beats the old one."
N[8]="So you can hand it a whole trip, three cities, three matches, and get one plan where every venue, route and detail is grounded, or honestly flagged when the records fall short."
N[9]="Gaffer. Built on Google's Agent Development Kit and Gemini. Kept honest by Arize Phoenix. Everything for the World Cup. Nothing made up."
: > durations.txt
for i in $(seq 1 9); do
  aws polly synthesize-speech --engine "$ENGINE" --voice-id "$VOICE" \
    --output-format mp3 --text "${N[$i]}" "s$i.mp3" >/dev/null
  $FF -y -loglevel error -i "s$i.mp3" -ar 48000 -ac 2 "s$i.wav"
  d=$($FP -v error -show_entries format=duration -of csv=p=0 "s$i.wav")
  echo "$i $d" | tee -a durations.txt
done
echo "=== total ==="; awk '{s+=$2} END{print s" sec ('"$VOICE"'/'"$ENGINE"')"}' durations.txt