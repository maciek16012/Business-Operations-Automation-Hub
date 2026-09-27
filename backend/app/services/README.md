# Application services

`cases.py` implements the transactional vertical slice and audit recording. `exports.py` coordinates approved-data exports. `serialization.py` provides JSON-safe date/UUID/Decimal conversion. API handlers call these services; future repository extraction is optional, not required boilerplate.
