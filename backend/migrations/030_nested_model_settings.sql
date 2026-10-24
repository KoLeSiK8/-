BEGIN;

UPDATE app.model_settings
SET settings = (settings - 'threshold_low' - 'threshold_high' - 'churn_k' - 'churn_midpoint')
    || jsonb_build_object(
        'thresholds', jsonb_build_object(
            'low', settings->'threshold_low',
            'high', settings->'threshold_high'
        ),
        'churn_curve', jsonb_build_object(
            'k', settings->'churn_k',
            'midpoint', settings->'churn_midpoint'
        )
    )
WHERE settings ? 'threshold_low';

COMMIT;