"""Test the real Dhan SDK against a local binary WebSocket server, without credentials."""

import asyncio
from datetime import datetime
import json
import struct
from threading import Event, Thread
import time

from dhanhq import DhanContext, MarketFeed
from websockets.asyncio.server import serve

from pipeline.services.feed_receiver import FeedReceiver
from pipeline.stages.intra_finder import IntraFinder


def main() -> None:
    ready, pong_received = Event(), Event()
    server_loop = asyncio.new_event_loop()
    state = {"port": 0, "subscription_sizes": [], "errors": []}
    stop = asyncio.Event()

    async def handler(socket):
        try:
            while sum(state["subscription_sizes"]) < 250:
                message = json.loads(await socket.recv())
                state["subscription_sizes"].append(message["InstrumentCount"])
            depth = b"".join(struct.pack("<IIHHff", 1000, 1000, 10, 10, 99.99 - i * 0.01, 100.01 + i * 0.01)
                             for i in range(5))
            for index in range(20):
                packet = struct.pack("<BHBIfHIfIIIIIIffff100s", 8, 162, 1, index + 1,
                                     100.0, 10, int(time.time()), 100.0,
                                     1000 + index, 2000, 2000, 0, 0, 0,
                                     99.0, 99.0, 101.0, 98.0, depth)
                await socket.send(packet)
            pong = await socket.ping()
            await asyncio.wait_for(pong, 2)
            pong_received.set()
            await socket.wait_closed()
        except Exception as exc:
            state["errors"].append(type(exc).__name__)

    async def run_server():
        async with serve(handler, "127.0.0.1", 0) as server:
            state["port"] = server.sockets[0].getsockname()[1]
            ready.set()
            await stop.wait()

    def serve_in_thread():
        asyncio.set_event_loop(server_loop)
        server_loop.run_until_complete(run_server())
        server_loop.close()

    thread = Thread(target=serve_in_thread, daemon=True)
    thread.start()
    if not ready.wait(5):
        raise RuntimeError("local WebSocket server did not start")
    MarketFeed.market_feed_wss = f"ws://127.0.0.1:{state['port']}"
    feed = MarketFeed(DhanContext("offline", "offline"), [(MarketFeed.NSE, str(i + 1), MarketFeed.Full) for i in range(250)], version="v2")
    try:
        feed.run_forever()
        receiver = FeedReceiver(feed, datetime.now, capacity=2)
        feed._trader_receiver = receiver
        receiver.start()
        if not pong_received.wait(3):
            raise AssertionError("server ping was not answered while consumer was idle")
        packets = [receiver.get(2).packet for _ in range(20)]
        assert [packet["security_id"] for packet in packets] == list(range(1, 21))
        assert all(len(packet["depth"]) == 5 and packet["LTP"] == "100.00" for packet in packets)
        assert max(state["subscription_sizes"]) <= 100
        assert not state["errors"], state["errors"]
        print(json.dumps({"packets": len(packets), "subscription_sizes": state["subscription_sizes"],
                          "pong_while_consumer_idle": True, "queue_high_water": receiver.high_water}))
    finally:
        IntraFinder._close_feed(feed)
        server_loop.call_soon_threadsafe(stop.set)
        thread.join(5)


if __name__ == "__main__":
    main()
