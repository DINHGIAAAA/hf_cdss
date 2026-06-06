# Dose Checking

Checks dose constraints and renal adjustment warnings for recommended medication classes.

Week-7 scope is deterministic and intentionally conservative. The module flags when a
clinician should review dose or continuation; it does not calculate patient-specific
doses.

Implemented checks:

- `digoxin` with reduced or missing eGFR.
- MRA agents (`spironolactone`, `eplerenone`, `finerenone`) with low eGFR or elevated potassium.
- Loop diuretics (`furosemide`, `bumetanide`, `torsemide`) requiring electrolyte, renal, BP, and volume monitoring.
- Evidence-based beta blockers (`metoprolol`, `bisoprolol`, `carvedilol`) with low or missing heart rate.

