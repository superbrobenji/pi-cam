# WebSocket Status Detail Design

**Date:** 2026-06-04

## Problem

The LIVE tab WebSocket indicator shows only a dot and the word "WebSocket". When it goes red there is no indication of why it disconnected, when it will reconnect, or how many clients are currently connected.

## Goals

- Show human-readable connection state (Connected / Reconnecting / Disconnected)
- Show connected client count when online (from `ws_clients` in health snapshot)
- Show close reason when offline (code + label)
- Show reconnect countdown during backoff

## Out of Scope

- Backend changes (all data is already available client-side)
- Persistent disconnect history

---

## Design

### HTML

Replace the current `ws-row` div:
```html
<div class="ws-row">
    <span class="dot err" id="live-ws-dot"></span>
    <span>WebSocket</span>
</div>
```

With an expanded block:
```html
<div class="ws-row">
    <span class="dot err" id="live-ws-dot"></span>
    <span id="live-ws-status">Connecting…</span>
    <span id="live-ws-detail" style="color:#555;font-size:0.75rem;margin-left:0.5rem"></span>
</div>
```

- `live-ws-status` — primary text: "Connected", "Reconnecting", "Disconnected"
- `live-ws-detail` — secondary text: client count when connected, countdown when reconnecting, close reason when disconnected

### States

**Connected:**
- Dot: `dot.ok`
- Status: "Connected"
- Detail: "N client" / "N clients" (from `ws_clients` field in health data)

**Reconnecting:**
- Dot: `dot.warn` (orange)
- Status: "Reconnecting"
- Detail: "in Xs…" — countdown updated every second via `setInterval`
- Countdown is derived from `wsDelay` at the time of disconnect

**Disconnected (no more retries — not applicable here since retries are infinite):**
- Handled as "Reconnecting" since the client always retries

**On close event (before reconnect fires):**
- Dot: `dot.err`
- Status: "Disconnected"
- Detail: close code label (see table below)

### Close code labels

| Code | Label |
|---|---|
| 1000 | Normal closure |
| 1001 | Going away |
| 1006 | Abnormal closure |
| 1011 | Server error |
| Other | Code NNNN |

### Client count

`ws_clients` is already polled via `pollLive()` → `/api/status`. When connected, the detail span is updated each health poll cycle with the latest count.

### JS changes

- `connectWS()`: on open → set status to "Connected", update detail with client count
- `ws.onclose/onerror`: set dot to err, status to "Disconnected", detail to close label; start countdown interval
- New `_wsCountdownTimer` — cleared on open, set on close to count down `wsDelay/1000` seconds
- `pollLive()`: when WS is open, update detail with `d.ws_clients`

---

## Files changed

| File | Change |
|---|---|
| `monitor_static/index.html` | Expand ws-row HTML, update JS state machine |
