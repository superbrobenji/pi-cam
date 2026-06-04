# WebSocket Integration Guide

The WebSocket endpoint pushes a people-tracking message every ~1 second.

## Connection

```
ws://<pi-ip>:8000/ws
```

## Message Format

```json
{
  "rawCount": 5,
  "enteredFrame": 2,
  "firstSeen": 1,
  "uniqueTotal": 14
}
```

| Field | Type | Description |
|---|---|---|
| `rawCount` | int | Total people currently visible in frame |
| `enteredFrame` | int | People not present in the previous tick (re-entry counts again) |
| `firstSeen` | int | People appearing for the first time this session |
| `uniqueTotal` | int | Cumulative unique people seen since app start |

All fields are always integers. `firstSeen` and `enteredFrame` are per-tick deltas — they reset each message. `uniqueTotal` only ever increases (resets to 0 on app restart, or when reset via `POST /control/reset-tracking`).

---

## Examples

### JavaScript (Browser)

```javascript
const ws = new WebSocket('ws://raspberrypi.local:8000/ws');

ws.onmessage = (event) => {
  const { rawCount, enteredFrame, firstSeen, uniqueTotal } = JSON.parse(event.data);
  console.log(`In frame: ${rawCount}, entered: ${enteredFrame}, new today: ${uniqueTotal}`);
};
```

### JavaScript (with reconnect)

```javascript
let retryDelay = 1000;

function connect() {
  const ws = new WebSocket('ws://raspberrypi.local:8000/ws');

  ws.onmessage = (event) => {
    const { rawCount, enteredFrame, firstSeen, uniqueTotal } = JSON.parse(event.data);
    console.log(`In frame: ${rawCount} | Entered: ${enteredFrame} | First seen: ${firstSeen} | Total unique: ${uniqueTotal}`);
    retryDelay = 1000;
  };

  ws.onclose = ws.onerror = () => {
    setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 30000);
  };
}

connect();
```

### Python

```python
import asyncio
import json
import websockets

async def main():
    uri = "ws://raspberrypi.local:8000/ws"
    async with websockets.connect(uri) as ws:
        async for message in ws:
            data = json.loads(message)
            print(
                f"In frame: {data['rawCount']} | "
                f"Entered: {data['enteredFrame']} | "
                f"First seen: {data['firstSeen']} | "
                f"Total unique: {data['uniqueTotal']}"
            )

asyncio.run(main())
```

Install dependency: `pip install websockets`

### Node.js

```javascript
const WebSocket = require('ws');

const ws = new WebSocket('ws://raspberrypi.local:8000/ws');

ws.on('message', (data) => {
  const { rawCount, enteredFrame, firstSeen, uniqueTotal } = JSON.parse(data);
  console.log(`In frame: ${rawCount} | Entered: ${enteredFrame} | First seen: ${firstSeen} | Total unique: ${uniqueTotal}`);
});
```

Install dependency: `npm install ws`

---

## Resetting the unique total

Send a POST request to reset `uniqueTotal` and `firstSeen` back to 0:

```bash
curl -X POST http://<pi-ip>:8000/control/reset-tracking
```

Or via the monitor dashboard at `http://<pi-ip>:8001` → LIVE tab → "Reset Unique Count".

---

## Notes

- Messages arrive every ~1 second regardless of whether values changed.
- The server pushes updates — the client never needs to send anything.
- Replace `raspberrypi.local` with the Pi's IP address if mDNS isn't available.
- `enteredFrame` and `firstSeen` will be `0` in mock camera mode (`MOCK_CAMERA=1`) as tracking requires a real camera.
- The `/health` endpoint (`GET /health`) returns camera and model status if you need to check whether detection is active.
