"""GrowthScope — open-source Marketing & Growth Intelligence toolkit for e-commerce.

GrowthScope analyses the public Google Analytics 4 (GA4) sample e-commerce export
(`bigquery-public-data.ga4_obfuscated_sample_ecommerce`) to produce funnel,
retention and attribution intelligence that a marketing team can act on.

This top-level package intentionally stays minimal: sub-packages own the real
logic (`growthscope.quality` validates the aggregates that the SQL exploration
queries return).
"""

__version__ = "0.1.0"
