# WebSocket Integration Guide

The WebSocket endpoint pushes a people-count message every ~1 second.

## Connection

```
ws://<pi-ip>:8000/ws
```

## Message Format

```json
{"count": 3}
```

`count` is always an integer — the number of people currently detected in frame.

---

## Examples

### JavaScript (Browser)

```javascript
const ws = new WebSocket('ws://raspberrypi.local:8000/ws');

ws.onmessage = (event) => {
  const { count } = JSON.parse(event.data);
  console.log(`People in frame: ${count}`);
};
```

### JavaScript (with reconnect)

```javascript
let retryDelay = 1000;

function connect() {
  const ws = new WebSocket('ws://raspberrypi.local:8000/ws');

  ws.onmessage = (event) => {
    const { count } = JSON.parse(event.data);
    console.log(`People in frame: ${count}`);
    retryDelay = 1000; // reset on successful message
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
            print(f"People in frame: {data['count']}")

asyncio.run(main())
```

Install dependency: `pip install websockets`

### Node.js

```javascript
const WebSocket = require('ws');

const ws = new WebSocket('ws://raspberrypi.local:8000/ws');

ws.on('message', (data) => {
  const { count } = JSON.parse(data);
  console.log(`People in frame: ${count}`);
});
```

Install dependency: `npm install ws`

---

## Notes

- Messages arrive every ~1 second regardless of whether the count changed.
- The server pushes updates — the client never needs to send anything.
- Replace `raspberrypi.local` with the Pi's IP address if mDNS isn't available.
- The `/health` endpoint (`GET /health`) returns camera and model status if you need to check whether detection is active before trusting the count.
