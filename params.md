Parameter	Default	What It Does	How To Adjust
MODE	LEVEL10	Switch strategy profile	TESTING=safe, NORMAL=balanced, LEVEL10=aggressive
MIN_PROB	0.50	Minimum model probability to enter	Higher = fewer trades / higher conviction; Lower = more trades
NORMAL_MIN_PROB	51.0	MC threshold for normal mode	≥51% combined edge required
RELAXED_MIN_PROB	50.0	MC threshold for LEVEL10	≥50% average edge allowed
STRENGTH_GAP_THRESHOLD	10	Currency strength spread	Lower = easier to qualify; Higher = only strongest pairs
MC_TP_MAX_BAND_PCT	0.7	Take‑profit limit vs MC range	0.7=use up to 70% of range; 0.8=wider; 0.6=tighter