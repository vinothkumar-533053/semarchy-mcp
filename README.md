# Semarchy MCP Server

An Model Context Protocol (MCP) prototype for Semarchy xDM.

MCP is a protocol for connecting large language models (LLMs) to external data sources, allowing LLMs to retrieve and manipulate data in real time.
This project provides a prototype MCP server that connects to Semarchy xDM, allowing LLMs to access and manipulate data in Semarchy xDM.

## Setup

//TODO: Test the setup steps from the source code.

Requirements:

- Python 3.11 and above.
- `uv` package manager. Use `brew install uv` to install on MacOS.

To setup the project:

1. Unzip the `semarchy-mcp.zip` archive to a folder.
2. Open a terminal this folder.
3. Run the following commands to create the virtual environment:
    ```bash
    # Create the Python virtual environment
    uv venv

    # Activate the virtual environment
    source .venv/bin/activate

    # Install the dependencies
    uv sync
    ```

## Play with MCP

You do not need to run the MCP server. The client will run the server.

### (Optional) Test with the MCP Inspector

The MCP inspector is a tool provided by Anthropic to test the various endpoints exposed by an MCP Server, exposing a web interface to test the various endpoints.

It is not required to run the MCP server, but it is a good way to test the server and see how it behaves.

```bash
npx @modelcontextprotocol/inspector uv --directory <your project folder>/semarchy-mcp run --env-file .env mcp-server.py
```

Note that:
- You should replace in the command `<your project folder>` with the folder containing the mcp-server code.
- You should create a `.env` file in the folder of the mcp-server, to give the xDM connection configuration. This file is referenced in the command above, and an example is provided below.

```properties
# .env file for MCP Server

# xDM Configuration
XDM_BASE_URL=http://localhost:8088/semarchy
XDM_USERNAME=semadmin
XDM_PASSWORD=xxxxxx
# The API key supercdes the user/password authentication if both are provided.
XDM_API_KEY=xxxxxxxxx 
# Default xDM data location: This is the location that will be used if no data location is specified in the request.
XDM_DATA_LOCATION=ProductRetailDemo
```

### MCP Tools

In addition to `get_model_description` (entities, attributes and references) and `query_data`
(SemQL queries), the server exposes governance metadata tools:

- `list_models()`: models available in the Semarchy repository.
- `get_entity_enrichers(entity, model_name?)`: enrichers configured on an entity, in execution order.
- `get_entity_validations(entity, model_name?)`: mandatory attributes, LOV-validated attributes, unique keys and row check constraints for an entity.
- `get_entity_match_rules(entity, model_name?)`: matcher configuration and match rules (duplicate detection conditions) for an entity.
- `get_entity_survivorship_rules(entity, model_name?)`: survivorship rules describing how golden records are consolidated from master records.
- `list_publishers(model_name?)`: publishers defined in the model.
- `list_lov_types(model_name?)`: LOV (List Of Values) types defined in the model, with their allowed values.

The xDM App Builder REST API's `get-data-model` endpoint only returns the logical model needed
for SemQL queries — it does not include this governance metadata. These tools instead fetch the
full export of the latest edition of a model directly from the Semarchy repository (via the
"List models", "List model editions" and "Export model edition" endpoints) and parse it live;
nothing is read from a static file. `model_name` is optional: if omitted and the repository has
only one model, that model is used automatically; if several models exist, the tool reports the
available names so the user can pick one and retry with `model_name` set.

### Play with Claude Desktop

Claude Desktop provides support for MCP server.

1. Install Claude Desktop from [Anthropic](https://claude.ai/download).
2. Open the app and login.
3. Edit the Claude Desktop Configuration file in `~/Library/Application Support/Claude/claude_desktop_config.json` and add the following code. Make sure to update:
    - `<your project folder>` with folder into which the semarchy-mcp project is installed
    - the various pieces in the `env` section with your xDM connection information.
        ```json
        {
            "mcpServers": {
                "Semarchy DM": {
                    "command": "uv",
                    "args": [
                        "--directory",
                        "<your project folder>/semarchy-mcp",
                        "run",
                        "mcp-server.py"
                    ],
                    "env": {
                        "XDM_BASE_URL": "http://localhost:8088/semarchy",
                        "XDM_USERNAME": "<user name>",
                        "XDM_PASSWORD": "<user password>",
                        "XDM_API_KEY": "<api key, supercedes user/password authentication>"
                    }
                }
            }
        }
        ```
4. Restart Claude Desktop.
5. Enter a prompt, such as:
    * *Return the top 10 customers in CustomerB2CDemo*
6. Continue the conversation with more complex requests, such as:
    * *Can you tell how many of these customers are female?*
    * *Can you return all fields for Antonia Mattos and Toni Mattos and put them side by side so that I can compare them?*

> NOTE: Claude used Anthropic's models, which have a daily limit with a free account.

## Next Steps

- Implement a dedicated Chat Agent with a Chainlit interface, removing the need for Claude Desktop and allowing the choice of the LLM.
- Implement error management in tools for the LLM to report meaningful errors to the user.
- Implement additional MCP endpoints to support more complex use cases.
- Convert the APIs to MCP endpoints.

## Contributing

This section is for contributors to the MCP server project, or developers desiring to start a new MCP server project.

### Original Setup

This section describes the original setup of the MCP server project. It is given here for reference only, should you want to recreate a project from scratch.

#### Create the project

```bash
uv init semarchy-mcp
cd semarchy-mcp
```

#### Create and activate a virtual environment

```bash
uv venv
source .venv/bin/activate
```

#### Install the dependencies

```bash
uv add "mcp[cli]" httpx requests
```