-- Seed script to add Google Calendar Events signal configuration
-- Run this to enable Google Calendar signal processing

-- First, ensure the google source exists
INSERT INTO source_configs (name, display_name, auth_type, platform, company, description, created_at, updated_at)
VALUES (
    'google',
    'Google',
    'oauth2',
    'cloud',
    'google',
    'Google services including Calendar, Gmail, and Drive',
    NOW(),
    NOW()
)
ON CONFLICT (name) DO NOTHING;

-- Insert the Google Calendar Events signal configuration
INSERT INTO signal_configs (
    signal_name,
    display_name,
    unit_ucum,
    computation,
    fidelity_score,
    macro_weight,
    min_transition_gap,
    source_name,
    stream_name,
    description,
    settings,
    created_at,
    updated_at
) VALUES (
    'google_calendar_events',
    'Calendar Events',
    '1', -- Dimensionless unit for discrete events
    '{
        "algorithm": "event_detection",
        "analysis_type": "categorical",
        "value_type": "discrete"
    }'::json,
    0.95, -- High fidelity for calendar data
    0.7,  -- Macro weight from _signal.yaml
    1800, -- 30 minutes min gap from _signal.yaml
    'google',
    'google_calendar',
    'Calendar events and meetings',
    '{
        "event_types": ["meeting", "focus_time", "out_of_office", "appointment", "reminder"],
        "confidence_threshold": 0.85
    }'::json,
    NOW(),
    NOW()
)
ON CONFLICT (signal_name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    unit_ucum = EXCLUDED.unit_ucum,
    computation = EXCLUDED.computation,
    fidelity_score = EXCLUDED.fidelity_score,
    macro_weight = EXCLUDED.macro_weight,
    min_transition_gap = EXCLUDED.min_transition_gap,
    description = EXCLUDED.description,
    settings = EXCLUDED.settings,
    updated_at = NOW();

-- Verify the insertion
SELECT 
    id,
    signal_name,
    display_name,
    source_name,
    stream_name,
    unit_ucum,
    computation
FROM signal_configs 
WHERE signal_name = 'google_calendar_events';