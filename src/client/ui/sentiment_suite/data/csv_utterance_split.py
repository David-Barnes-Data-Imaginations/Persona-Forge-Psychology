import pandas as pd

# Load your cleaned CSV
input_csv = "early_carl_and_gloria.csv"
df = pd.read_csv(input_csv)
df["utterance_num"] = range(1, len(df) + 1)
# Make sure the speaker column is consistent
if 'speaker' not in df.columns or 'line' not in df.columns:
    raise ValueError("Expected columns 'speaker' and 'line' not found.")

# Generate utterance numbers that increment only when speaker changes
df['utterance_num'] = (df['speaker'] != df['speaker'].shift()).cumsum()

# Rename 'line' to 'utterance' for clarity
df = df.rename(columns={'line': 'utterance'})

# Save single combined version for dashboard/graph input
df.to_csv("glor_carl_numbered_combined.csv", index=False)

# Optional: also split into therapist/client versions for manual analysis or tab-specific dashboards
therapist_df = df[df['speaker'].str.lower() == 'therapist']
client_df = df[df['speaker'].str.lower() == 'patient']

therapist_df.to_csv("gloria_therapist.csv", index=False)
client_df.to_csv("gloria_client.csv", index=False)
