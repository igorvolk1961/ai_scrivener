import asyncio

async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()

async def handle(reader, writer):
    try:
        remote_r, remote_w = await asyncio.open_connection("postgres", 5432)
    except Exception:
        writer.close()
        return
    await asyncio.gather(pipe(reader, remote_w), pipe(remote_r, writer))

async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", 5432)
    async with server:
        await server.serve_forever()

asyncio.run(main())
