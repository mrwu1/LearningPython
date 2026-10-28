





stream = agent.stream_events(input, version="v3")

# Use stream.values for state snapshots

for snapshot in stream.values:
    print(snapshot)

final_state = stream.output

# stream.output for the final agent state.