# Physical infrastructure hierarchy

HIOP v3 introduces a nullable, property-aware hierarchy:
Organization → Property → Building → Floor → Zone → Department → Room → Device.

Buildings, floors, and zones are managed through `/api/v1/buildings`,
`/api/v1/floors`, and `/api/v1/zones`. Reads are available to administrators and
technicians; mutations are administrator-only. Delete actions safely deactivate
records and preserve history. Existing rooms, departments, and devices receive
nullable location references so legacy data remains valid.

Indoor maps, floor plans, GPS, and automatic device placement are not included.
