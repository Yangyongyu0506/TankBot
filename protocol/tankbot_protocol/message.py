"""Dependency-free public envelope construction, shared by every Python runtime."""
def envelope(schema, channel, payload, *, tick, hz, run_id, publisher_id, sequence,
             frame_id=None, message_type="topic", request_id=None):
    return dict(protocol_version="1.0", message_type=message_type, channel=channel,
                sequence_number=sequence, simulation_tick=tick,
                simulation_time_ns=tick * 1_000_000_000 // hz, run_id=run_id,
                publisher_id=publisher_id, request_id=request_id, frame_id=frame_id,
                schema=schema, payload=payload)

