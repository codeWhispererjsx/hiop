# API Documentation

Version: 1.0

---

# Authentication

POST /api/auth/login

POST /api/auth/logout

GET /api/auth/me

---

# Dashboard

GET /api/dashboard

Returns:

- Online Devices
- Offline Devices
- Active Alerts
- Maintenance Tickets
- Recent Activity

---

# Devices

GET /api/devices

GET /api/devices/{id}

POST /api/devices

PUT /api/devices/{id}

DELETE /api/devices/{id}

---

# Scanner

POST /api/scanner/start

POST /api/scanner/stop

GET /api/scanner/status

GET /api/scanner/history

---

# Alerts

GET /api/alerts

PUT /api/alerts/{id}/acknowledge

PUT /api/alerts/{id}/resolve

---

# Maintenance

GET /api/maintenance

POST /api/maintenance

PUT /api/maintenance/{id}

DELETE /api/maintenance/{id}

---

# Reports

GET /api/reports/inventory

GET /api/reports/offline-devices

GET /api/reports/maintenance