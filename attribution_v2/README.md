# Attribution V2 — 4 Independent Profiles

## Structure


attribution_v2/

├── attribution_core.py       # Shared calculation engine

├── profile_runner.py         # Single / all profiles runner

├── profile_logger.py         # Independent JSONL logger per profile

├── profiles/

│   └── attribution_profiles.py   # 4 profile definitions

├── tests/                    # Unit tests

├── logs/                     # Per-profile output

│   ├── pf-a/

│   ├── pf-b/

│   ├── pf-c/

│   └── pf-d/

└── examples/                 # Demo scripts
