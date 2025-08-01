import pandas as pd
import re

# Load the file with a more flexible approach
with open("carl_and_gloria_from_pdf.csv", "r") as file:
    lines = file.readlines()

# Clean and extract utterances
utterances = []
current_utterance = ""
current_speaker = None

for line in lines:
    line = line.strip()
    speaker_match = re.match(r"^([TC])(\d+)", line)

    if speaker_match:
        # If we have a complete utterance, add it
        if current_utterance and current_speaker:
            utterances.append({
                'speaker': 'Therapist' if current_speaker == 'T' else 'Client',
                'utterance_num': current_utterance_num,
                'utterance': current_utterance.strip()
            })
        # Start a new utterance
        current_speaker = speaker_match.group(1)
        current_utterance_num = speaker_match.group(2)
        current_utterance = re.sub(r"^[TC]\d+\s*", "", line)
    elif line and not line.startswith("Rogers' Transcripts"):  # Skip page headers
        # Continue current utterance
        current_utterance += " " + line

# Add the last utterance if there is one
if current_utterance and current_speaker:
    utterances.append({
        'speaker': 'Therapist' if current_speaker == 'T' else 'Client',
        'utterance_num': current_utterance_num,
        'utterance': current_utterance.strip()
    })

# Clean the utterances
cleaned_utterances = []
for item in utterances:
    # Remove inline notes like (T: Mhm) or (C: smiles)
    cleaned = re.sub(r"\([^)]*\)", "", item['utterance']).strip()
    if cleaned:
        cleaned_utterances.append({
            'speaker': item['speaker'],
            'utterance_num': item['utterance_num'],
            'utterance': cleaned
        })

# Build final cleaned dataframe
clean_df = pd.DataFrame(cleaned_utterances)

# Preview the result
print("\nSample of cleaned dialogue:")
print(clean_df.head(10))

# Create the output directory if it doesn't exist
import os
os.makedirs("converted_csvs", exist_ok=True)

# Export
clean_df.to_csv("converted_csvs/cleaned_carl_and_gloria.csv", index=False)
print("\nSaved cleaned CSV to converted_csvs/cleaned_carl_and_gloria.csv")

# Also create separate files for each speaker
therapist_df = clean_df[clean_df['speaker'] == 'Therapist']
client_df = clean_df[clean_df['speaker'] == 'Client']

therapist_df.to_csv("converted_csvs/therapist_utterances.csv", index=False)
client_df.to_csv("converted_csvs/client_utterances.csv", index=False)
print("\nSaved separate files for Therapist and Client utterances")