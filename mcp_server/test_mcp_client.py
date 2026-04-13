import asyncio
from fastmcp import Client
async def test_mcp_direct_http():
    # URL basato sulla nuova configurazione:
    # app.mount("/mcp_app", mcp_app) in main.py
    # mcp.http_app(path="/mcp") in server.py
    url = "http://localhost:8000/mcp-app"

    try:
        client= Client(url)
        print('ok per client')
        async with client:
            pong= await client.ping()
            print("Ping response:", pong)

            # 🔹 2. Lista tools
            tools = await client.list_tools()
            print("\nTools disponibili:")
            for tool in tools:
                print("-", tool.name)

                # 🔹 3. Call tool
            result = await client.call_tool(
                "hello_tool",
                {"name": "Andrea"}
            )
            print("\nRisultato tool:")
            print(result)

                
    except Exception as e:
        print(f"❌ Errore di connessione: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp_direct_http())
