"""
mcp-server.py

This module initializes and runs a FastMCP server for interacting with Semarchy Data Management (DM) via a Model Context Protocol (MCP) interface. It exposes resources and tools for listing data locations, retrieving model descriptions, querying data using SemQL, inspecting MDM governance metadata (enrichers, validations, match rules, survivorship rules, publishers, LOV types), and generating prompts to convert natural language queries into SemQL queries or answer governance questions.

Key Components:
- FastMCP server initialization for the 'semarchy-dm' service.
- DMClient initialization using environment variables for connection details.
- Resource and tool endpoints for:
    - Listing available data locations.
    - Retrieving model descriptions for a given data location.
    - Executing SemQL queries and returning results.
    - Listing available models, and listing enrichers, validations, match rules and survivorship rules for a given entity.
    - Listing available publishers and LOV types.
    - Generating prompts to convert natural language queries into SemQL queries, or to answer governance questions.

Governance metadata (enrichers, validations, match rules, survivorship rules, publishers,
LOV types) is not exposed by the xDM App Builder REST API's `get-data-model` endpoint. It is
only present in a model edition's full export, so it is always fetched live from the Semarchy
repository via DMClient.export_model_edition and parsed with ModelXmlClient; a model, once
fetched, is cached in memory for the life of the server process.

Usage:
- The server is started with the 'stdio' transport when run as the main module.
"""

from mcp.server.fastmcp import FastMCP
from typing import List, Optional, Tuple
import os
import json
from DMClient import DMClient
from DMClient import SemqlQuery
from ModelXmlClient import ModelXmlClient


# Initialize FastMCP server
mcp = FastMCP("semarchy-dm", port=8001)

# Initialize DMClient with the connection information passed as environment variables.
dm_client = DMClient(
    base_url=os.environ.get("XDM_BASE_URL") if os.environ.get("XDM_BASE_URL") else "",
    default_data_location=os.environ.get("XDM_DATA_LOCATION") if os.environ.get("XDM_DATA_LOCATION") else "",
    username=os.environ.get("XDM_USERNAME") if os.environ.get("XDM_USERNAME") else "",
    password=os.environ.get("XDM_PASSWORD") if os.environ.get("XDM_PASSWORD") else "",
    api_key=os.environ.get("XDM_API_KEY") if os.environ.get("XDM_API_KEY") else ""
    )

# Model edition exports are fetched live from the repository on first use and cached here,
# keyed by model name, for the life of the server process.
_model_clients: dict[str, ModelXmlClient] = {}


def _resolve_model_client(model_name: Optional[str] = None) -> Tuple[Optional[ModelXmlClient], Optional[str]]:
    """
    Resolves the ModelXmlClient to use for a governance metadata query, fetching and
    caching the model edition export from the Semarchy repository if needed.

    Args:
        model_name: The name of the model to use. If not provided, and the repository
            has exactly one model, that model is used. If not provided and the
            repository has several models, no client is resolved and the caller should
            report the available models so the user can pick one.

    Returns:
        A (client, error) tuple: on success, (ModelXmlClient, None); on failure,
        (None, error message to return to the caller).
    """
    if not model_name:
        models = dm_client.list_models()
        if not models:
            return None, "No models were found in the Semarchy repository."
        if len(models) > 1:
            names = ", ".join(model["name"] for model in models)
            return None, (
                f"Several models are available in the repository: {names}. "
                "Please specify which one to use via the 'model_name' parameter."
            )
        model_name = models[0]["name"]

    if model_name not in _model_clients:
        edition_key = dm_client.get_latest_model_edition_key(model_name)
        xml_content = dm_client.export_model_edition(model_name, edition_key)
        client = ModelXmlClient()
        client.load(xml_content)
        _model_clients[model_name] = client

    return _model_clients[model_name], None


@mcp.resource("semarchy://data-locations")
def get_available_data_locations() -> str:
    """
    List all available data locations.
    
    Returns:
        A list of data locations
    """
    data_locations = dm_client.list_data_locations()
    if data_locations:
        return dm_client.data_locations_to_prompt(data_locations)
    else:
        return "No data locations found."

@mcp.tool()
def get_model_description(datalocation: str) -> str:
    """
    Get a model description for a given data location.
    
    Args:
        datalocation: The data location to describe
        
    Returns:
        Model description in a readable format
    """
    model = dm_client.read_model(datalocation)
    if model:
        dm_client.default_data_location = datalocation
        return dm_client.model_to_prompt(model)
    else:
        return f"Model for data location {datalocation} not found."

@mcp.tool()
def query_data(query: SemqlQuery) -> str:
    """
    Query data from a given data location in natural language.
    
    Args:
        query: A SemQL query object to execute
        datalocation (Optional): The data location to query.
        
    Returns:
        Query results in a readable format
    """

    data = dm_client.read_data(query)

    if data:
        return data
    else:
        return f"Query returned no data. Here is the query: {query}"


@mcp.tool()
def list_models() -> str:
    """
    List the models available in the Semarchy repository. Use this to find the
    'model_name' to pass to the entity governance tools (enrichers, validations,
    match rules, survivorship rules) and to list_publishers/list_lov_types, when
    more than one model exists.

    Returns:
        The list of models in a readable format
    """
    models = dm_client.list_models()
    if not models:
        return "No models were found in the Semarchy repository."
    content = "# Models\n"
    for model in models:
        content += f"\n- name: {model.get('name')}\n  label: {model.get('label')}\n  usedIn (data locations): {', '.join(model.get('usedIn') or [])}"
    return content


@mcp.tool()
def get_entity_enrichers(entity: str, model_name: str = None) -> str:
    """
    List the enrichers (SemQL expressions or plugins) configured on an entity,
    in the order they are executed.

    Args:
        entity: The name of the entity to describe
        model_name (Optional): The model to use. If not provided and several
            models exist in the repository, the available models are returned
            so the user can pick one.

    Returns:
        The list of enrichers in a readable format
    """
    client, error = _resolve_model_client(model_name)
    if error:
        return error
    return client.enrichers_to_prompt(entity)


@mcp.tool()
def get_entity_validations(entity: str, model_name: str = None) -> str:
    """
    List the validations configured on an entity: mandatory attributes,
    LOV-validated attributes, unique keys and row check constraints.

    Args:
        entity: The name of the entity to describe
        model_name (Optional): The model to use. If not provided and several
            models exist in the repository, the available models are returned
            so the user can pick one.

    Returns:
        The list of validations in a readable format
    """
    client, error = _resolve_model_client(model_name)
    if error:
        return error
    return client.validations_to_prompt(entity)


@mcp.tool()
def get_entity_match_rules(entity: str, model_name: str = None) -> str:
    """
    List the matcher configuration and match rules (duplicate detection
    conditions) configured on an entity.

    Args:
        entity: The name of the entity to describe
        model_name (Optional): The model to use. If not provided and several
            models exist in the repository, the available models are returned
            so the user can pick one.

    Returns:
        The matcher configuration and match rules in a readable format
    """
    client, error = _resolve_model_client(model_name)
    if error:
        return error
    return client.match_rules_to_prompt(entity)


@mcp.tool()
def get_entity_survivorship_rules(entity: str, model_name: str = None) -> str:
    """
    List the survivorship rules configured on an entity, describing how
    golden record attributes are consolidated from master records.

    Args:
        entity: The name of the entity to describe
        model_name (Optional): The model to use. If not provided and several
            models exist in the repository, the available models are returned
            so the user can pick one.

    Returns:
        The list of survivorship rules in a readable format
    """
    client, error = _resolve_model_client(model_name)
    if error:
        return error
    return client.survivorship_rules_to_prompt(entity)


@mcp.tool()
def list_publishers(model_name: str = None) -> str:
    """
    List the publishers (source systems allowed to contribute data) defined
    in the model.

    Args:
        model_name (Optional): The model to use. If not provided and several
            models exist in the repository, the available models are returned
            so the user can pick one.

    Returns:
        The list of publishers in a readable format
    """
    client, error = _resolve_model_client(model_name)
    if error:
        return error
    return client.publishers_to_prompt()


@mcp.tool()
def list_lov_types(model_name: str = None) -> str:
    """
    List the List-Of-Values (LOV) types defined in the model, with their
    allowed values.

    Args:
        model_name (Optional): The model to use. If not provided and several
            models exist in the repository, the available models are returned
            so the user can pick one.

    Returns:
        The list of LOV types and their values in a readable format
    """
    client, error = _resolve_model_client(model_name)
    if error:
        return error
    return client.lov_types_to_prompt()


@mcp.prompt()
def generate_model_metadata_prompt(question: str, entity: str = None) -> str:
    """Generate a prompt to answer a governance question about the MDM model, such as
    which enrichers, validations, match rules or survivorship rules apply to an entity,
    or what publishers or LOV types are available."""
    return f"""Answer the following question about the MDM model's governance metadata: '{question}'

    Follow these instructions:
    1. If the question is about a specific entity{f" (here, '{entity}')" if entity else ""}, first identify the entity name using get_model_description if needed.
    2. Depending on the question, call one or more of the following tools:
       - get_entity_enrichers(entity, model_name?): to list the enrichers (data enrichment rules) configured on an entity.
       - get_entity_validations(entity, model_name?): to list the validations (mandatory attributes, LOV validations, unique keys, row check constraints) configured on an entity.
       - get_entity_match_rules(entity, model_name?): to list the matcher configuration and match rules (duplicate detection conditions) configured on an entity.
       - get_entity_survivorship_rules(entity, model_name?): to list the survivorship rules (how golden records are consolidated from master records) configured on an entity.
       - list_publishers(model_name?): to list the publishers (source systems) defined in the model.
       - list_lov_types(model_name?): to list the LOV (List Of Values) types defined in the model, with their allowed values.
    3. None of these tools require a 'model_name' if the repository only has one model. If a tool
       instead reports that several models are available, call list_models() to show them to the
       user and ask which one to use, then retry the same tool with that 'model_name'.
    4. Return the results in a clear, structured format, either as bullet points or as a table.
    5. If a tool reports that the entity was not found, report this to the user instead of guessing an answer."""


@mcp.prompt()
def generate_query_prompt(nlp_query: str, datalocation: str = None) -> str:
    """Generate a prompt to convert a natural language query to a SemqlQuery and search the corresponding records in data location."""
    return f"""Search for records in the data location using the query_data tool.

    Follow these instructions:
    1. First, retreive the DATA MODEL description using get_model_description(datalocation='{datalocation}')
    2. Then, convert the natural language query '{nlp_query}' into a SemqlQuery, extracting the following elements:
         - Entity: The entity to query
         - Filter: The SemQL filter condition to apply
         - Expressions: An array of SemQL expressions to retrieve
         - OrderBy: a SemQL expression order in which to sort the results
         - Limit: The maximum number of records to return
         - Offset: The starting point for the results
    3. Finally, execute the query using query_data(SemqlQuery)
    4. Return the results in a readable format.
    3. Provide a comprehensive summary that includes:
       - The various elements of the  SemQL query generated from '{nlp_query}'

    Organize the results in a clear, structured format, either as bullet points, or as a table.

    Follow these guidelines to generate the Filter, Expressions and OrderBy clauses:
    - Use the DATA MODEL to identify the entities and attributes.
    - Use the DATA MODEL to identify the relationships between entities.
    - Use the DATA MODEL to identify the attributes of the entities.
    - Use the DATA MODEL to identify the attributes of the parent entities.
    - Use the DATA MODEL to identify the attributes of the child entities.
    - Use the DATA MODEL to identify the validations of the entity.
    - Use the DATA MODEL to identify the enrichers of the entity.
    - SemQL is a language used to query data structured after DATA MODEL.
    - SemQL supports conditions, expressions, and order by clauses.
    - SemQL uses for conditions, expressions, and order by clauses the SQL syntax.
    - SemQL does NOT support full queries, SELECT, WHERE and JOIN clauses.
    - Entities are equivalent to SQL tables and are referred to by their 'name', in Camelcase.
    - Attributes are equivalent to SQL columns and are referred to by their 'name', in Camelcase.
    - SemQL uses DATA MODEL elements: Entity 'name', Attribute 'name', 'Child Reference Role Names' and 'Parent Reference Role Names'.
    - You can access attributes of a parent entity using the "<parent role name>.<attribute name>" syntax.
    - You can filter using attributes from a child entity using the "ANY <child role name> HAVING (<filter expression on the child record>)" syntax.
    - You can access attributes from the entity being queried using the <attribute name>.
    - For the entity being queries, NEVER prefix <attribute name> with the <entity name>.
    - Remove the "ORDER BY" keywords from order by clauses.
    - Do NOT specify a column or attribute with an alias the AS keyword.
    - Do NOT use the "SELECT" keyword."""

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')
