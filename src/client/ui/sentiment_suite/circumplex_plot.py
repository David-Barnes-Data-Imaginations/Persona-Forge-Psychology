import plotly.graph_objects as go
import pandas as pd
from emotion_mapping import modernbert_va_map

DEBUG = True
import math


def create_circumplex_plot(df, show_text=True):
    # Define Russell's Circumplex boundary (circle)
    theta = [i * (2 * math.pi) / 100 for i in range(101)]
    circle_x = [math.cos(t) for t in theta]
    circle_y = [math.sin(t) for t in theta]

    # Normalize valence/arousal to be within the circumplex circle
    magnitude = (df['valence'] ** 2 + df['arousal'] ** 2).pow(0.5)
    df['valence'] = df['valence'] / magnitude.where(magnitude > 1, 1)
    df['arousal'] = df['arousal'] / magnitude.where(magnitude > 1, 1)

    # Assign distinct colors per emotion
    unique_emotions = sorted(df['emotion'].unique())
    color_map = {emotion: f'hsl({i * 360 / len(unique_emotions)}, 70%, 60%)'
                 for i, emotion in enumerate(unique_emotions)}

    fig = go.Figure()

    # Add Circumplex circle (always visible as the first trace)
    fig.add_trace(go.Scatter(
        x=circle_x,
        y=circle_y,
        mode='lines',
        line=dict(color='white', dash='dot'),
        name='Russell Circumplex'
    ))

    # Add utterances per emotion
    for emotion in unique_emotions:
        emotion_df = df[df['emotion'] == emotion]
        fig.add_trace(go.Scatter(
            x=emotion_df['valence'],
            y=emotion_df['arousal'],
            mode='markers+text' if show_text else 'markers',
            marker=dict(size=10, color=color_map[emotion]),
            text=emotion_df['emotion'] if show_text else None,
            textposition='top center',
            name=emotion
        ))

    # Create dropdown buttons for emotions
    buttons = [
        dict(label="All Emotions",
             method="update",
             args=[{"visible": [True] * (len(unique_emotions) + 1)}])
    ]
    for i, emotion in enumerate(unique_emotions):
        visibility = [False] * (len(unique_emotions) + 1)
        visibility[0] = True  # Keep the circle visible
        visibility[i + 1] = True  # Show only this emotion
        buttons.append(
            dict(label=emotion,
                 method="update",
                 args=[{"visible": visibility}])
        )

    fig.update_layout(
        title="Russell Circumplex View of Valence-Arousal Space",
        width=700,  # Increase this value to make the graph bigger
        height=700,  # Increase this value to make the graph bigger
        xaxis=dict(
            title='Valence',
            range=[-1.05, 1.05],
            zeroline=False,
            showgrid=False,
            scaleanchor='y',
            scaleratio=1
        ),
        yaxis=dict(
            title='Arousal',
            range=[-1.05, 1.05],
            zeroline=False,
            showgrid=False
        ),
        plot_bgcolor='#0d0c1d',
        paper_bgcolor='#0d0c1d',
        font=dict(color='white'),
        shapes=[
            dict(type='line', x0=-1.05, y0=0, x1=1.05, y1=0, line=dict(color='grey', width=1)),
            dict(type='line', x0=0, y0=-1.05, x1=0, y1=1.05, line=dict(color='grey', width=1))
        ],
        updatemenus=[
            dict(
                buttons=buttons,
                direction="down",
                showactive=True,
                x=0,
                y=1.15,
                xanchor="left",
                yanchor="top"
            )
        ]
    )

    return fig
