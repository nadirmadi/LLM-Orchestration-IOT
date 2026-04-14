#pragma once

// ─────────────────────────────────────────────────────────────────
//  HttpAdapter — exposes the patient badge over HTTP so that the
//  Monitoring Agent can discover it (via GET /capabilities) and the
//  Orchestration Agent can send commands to it (wake/sleep/...).
//
//  The badge is always active by design, so /wake and /sleep are
//  implemented as no-ops that always return { "ok": true, "status":
//  "active" }. They exist only so the Orchestration Agent can call
//  them without crashing if it mistakenly treats the badge like a
//  normal fixed sensor.
// ─────────────────────────────────────────────────────────────────

void setupHttp();
void loopHttp();
