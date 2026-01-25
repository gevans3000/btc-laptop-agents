import pytest
import asyncio
from laptop_agents.data.providers.bitunix_websocket import BitunixWebsocketClient


@pytest.mark.asyncio
async def test_websocket_handle_push_candle():
    """Verify parsing of kline push messages."""
    client = BitunixWebsocketClient("BTCUSDT")
    msg_data = {
        "event": "channel_pushed",
        "data": {
            "kline": {
                "time": 1704067200000,
                "open": "40000",
                "high": "40500",
                "low": "39500",
                "close": "40200",
                "baseVol": "100",
            }
        },
    }

    client._handle_push(msg_data)
    candle = client.get_latest_candle()
    assert candle is not None
    assert candle.open == 40000.0
    assert candle.close == 40200.0
    assert "2024-01-01" in candle.ts


@pytest.mark.asyncio
async def test_websocket_zombie_detection():
    """Verify connection is detected as unhealthy if no messages received."""
    client = BitunixWebsocketClient("BTCUSDT")
    client._last_pong = asyncio.get_event_loop().time() - 70  # 70 seconds ago

    assert client.is_healthy() is False
