from fastmcp import FastMCP

# Creazione del server MCP
mcp = FastMCP("Fidelitree MCP")
mcp_app = mcp.http_app(path="/")

@mcp.tool()
def hello_tool(name: str = "World") -> str:
    """Quando viene richiesto di salutare qualcuno si risponde con questa frase"""
    return f"Hello, {name}! Questo è il server MCP di Fidelitree, ti sei connesso con mcp caro mio."

@mcp.resource("config://info")
def info_resource() -> str:
    """Una risorsa di prova che restituisce informazioni sul server."""
    return "Fidelitree MCP Server v0.1 - Running via FastMCP"


