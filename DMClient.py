from typing import List, Optional
from pydantic import BaseModel, Field
import requests
import warnings
import urllib

warnings.filterwarnings('ignore')


class SemqlQuery(BaseModel):
    '''
    Represents a SemQL query for the Semarchy Query REST API.
    
    Attributes:
        entity (str): Name of the entity to query. Must be a valid entity name from the DATA MODEL.
        expressions (Optional[List[str]]): List of SemQL expressions to return (e.g., ['ID', 'FirstName', 'Upper(LastName)']).
        filter (Optional[str]): SemQL filter condition to filter the records.
        order_by (Optional[str]): SemQL order by condition to sort the records.
        offset (Optional[int]): Offset for pagination.
        nb_records (Optional[int]): Number of records to return (default: 20).
    '''

    entity: str = Field(description="Name of the entity to query. If must be a valid entity name from the DATA MODEL", default=None)
    expressions: Optional[List[str]] = Field(description="Array of of SemQL expressions. For example ['ID', 'FirstName', 'Upper(LastName)']. Return None if no expressions are detected", default=None)
    filter: Optional[str] = Field(description="SemQL filter condition to filter the records. Return None if no filter is detected", default=None)
    order_by: Optional[str] = Field(description="SemQL order by condition to sort the records. Return None if no order by is detected", default=None)
    offset: Optional[int] = Field(description="Offset for pagination", default=None)
    nb_records: Optional[int] = Field(description="Number of records to return", default=20)


class DMClient:
    """
    Provides an interface to interact with the Semarchy REST API, allowing users to query data, retrieve data models, and list data locations.

    Attributes:
        base_url (str): The base URL for the Semarchy instance.
        default_data_location (str): The default data location to use for queries.
        username (str, optional): Username for basic authentication.
        password (str, optional): Password for basic authentication.
        api_key (str, optional): API key for authentication.
    """

    def __init__(self, base_url, default_data_location, username=None, password=None, api_key=None):
        """
        Initializes the DMClient with connection and authentication details.

        Args:
            base_url (str): The base URL for the Semarchy instance.
            default_data_location (str): The default data location to use for queries.
            username (str, optional): Username for basic authentication.
            password (str, optional): Password for basic authentication.
            api_key (str, optional): API key for authentication.
        """

        self.base_url = base_url
        self.default_data_location = default_data_location
        self.username = username
        self.password = password
        self.api_key = api_key

    def call_api(self, query_url):
        """
        Sends a GET request to the specified API endpoint using either API key or basic authentication.

        Args:
            query_url (str): The API endpoint to call (relative to base_url).

        Returns:
            Response: The response object from the requests library.
        """

        query_url = self.base_url + query_url
        if self.api_key:
            headers = {"API-Key": f"{self.api_key}"}
            response = requests.get(query_url, headers=headers)
        else:
            response = requests.get(
                query_url, auth=(self.username, self.password))
        return response

    def read_data(self, semql_query: SemqlQuery, data_location: str = None):
        """
        Executes a SemQL query against the specified or default data location and returns the query URL and response data.

        Args:
            semql_query (SemqlQuery): The SemQL query object to execute.
            data_location (str, optional): The data location to query. Defaults to the client's default_data_location.
        
        Returns:
            tuple: (query_url, data) where query_url is the constructed API URL and data is the response JSON.
        """
        
        if data_location == None:
            data_location = self.default_data_location

        entity = semql_query.entity

        limit = f"$limit={semql_query.nb_records}" if semql_query.nb_records else ""
        offset = f"&$offset={semql_query.offset}" if semql_query.offset else ""

        if semql_query.expressions:
            expressions = f"&$baseExprs=ID&$expr=" + "&$expr=".join(semql_query.expressions)
        else:
            "&$baseExprs=USER_ATTRS"


        filter = f"&$f={urllib.parse.quote_plus(semql_query.filter)}" if semql_query.filter else ""

        order_by = f"&$orderBy={urllib.parse.quote_plus(semql_query.order_by)}" if semql_query.order_by else ""

        query_url = f"/api/rest/query/{data_location}/{entity}/GD?{limit}{offset}{expressions}{filter}{order_by}"

        print(query_url)
        response = self.call_api(query_url)
        data = response.json()
        return query_url, data

    def read_model(self, data_location: str):
        """
        Retrieves the data model for the specified data location.

        Args:
            data_location (str): The data location for which to retrieve the model.
        
        Returns:
            dict: The data model as a dictionary.
        """

        query_url = f"/api/rest/app-builder/data-locations/{data_location}/get-data-model"
        response = self.call_api(query_url)
        data = response.json()
        print("Data Model Response: ", data)
        return data
    
    def list_data_locations(self):
        """
        Lists all available data locations.

        Returns:
            list: A list of data locations as dictionaries.
        """
        query_url = "/api/rest/app-builder/data-locations"
        response = self.call_api(query_url)
        data = response.json()
        return data

    def list_models(self):
        """
        Lists all models available in the Semarchy repository.

        Returns:
            list: A list of models as dictionaries (name, label, description, usedIn).
        """
        query_url = "/api/rest/app-builder/models"
        response = self.call_api(query_url)
        return response.json()

    def list_model_editions(self, model_name: str):
        """
        Lists the editions of a model.

        Args:
            model_name (str): The name of the model.

        Returns:
            list: A list of model editions as dictionaries, each with a 'key' (e.g. '0.0').
        """
        query_url = f"/api/rest/app-builder/models/{model_name}/editions"
        response = self.call_api(query_url)
        return response.json()

    def get_latest_model_edition_key(self, model_name: str) -> str:
        """
        Finds the most recent edition of a model.

        Args:
            model_name (str): The name of the model.

        Returns:
            str: The key (e.g. '0.0') of the latest model edition.
        """
        editions = self.list_model_editions(model_name)
        latest = max(editions, key=lambda e: tuple(int(p) for p in e["key"].split(".")))
        return latest["key"]

    def export_model_edition(self, model_name: str, edition_key: str) -> bytes:
        """
        Exports the full content (entities, enrichers, validations, match rules,
        survivorship rules, publishers, LOV types, ...) of a model edition as XML.

        Args:
            model_name (str): The name of the model.
            edition_key (str): The key (e.g. '0.0') of the model edition to export.

        Returns:
            bytes: The raw XML content of the model edition export.
        """
        query_url = f"/api/rest/app-builder/models/{model_name}/editions/{edition_key}/content"
        response = self.call_api(query_url)
        return response.content

    def data_locations_to_prompt(self, data_locations) -> str:
        """
        Formats a list of data locations into a human-readable string, suitable for a prompt.

        Args:
            data_locations (list): List of data location dictionaries.
        
        Returns:
            str: Formatted string describing available data locations.
        """
        content = "# Availble Data Locations\n"
        for data_location in data_locations:
            content += f"- Name: {data_location.get('name')}\n"
            content += f"  Label: {data_location.get('label')}\n"
            content += f"  Description: {data_location.get('description')}\n"
            content += f"  Type: {data_location.get('type')}\n"
            content += f"  Database Type: {data_location.get('dbType')}\n"
            content += f"  Model Name: {data_location.get('modelName')}\n"
        return content

    def model_to_prompt(self, model: any) -> str:
        """
        Formats a data model dictionary into a human-readable string prompt, including entities, attributes and references.

        Note: the xDM REST API model does not include enrichers, validations, match
        rules, survivorship rules, publishers or LOV types. Use ModelXmlClient for
        that governance metadata.

        Args:
            model (dict): The data model dictionary.

        Returns:
            str: Formatted string describing the model, its entities, attributes and references.
        """

        content = "# Model Description\n"
        content += "\n## Entities:\n"
        for entity in model.get('entities'):
            description = f"{entity.get('description')} {entity.get('documentation')}"
            description = f" - {description}" if description != " " else ""
            content += f"\n- name: {entity.get('name')}\n  description: {entity.get('label')}{description}.\n  attributes:"
            for attribute in entity.get("attributes"):
                description = f"{attribute.get('description')}{attribute.get('documentation')}"
                description = f" - {description}" if description != "" else ""
                content += f"\n\t- name: {attribute.get('name')}\n\t  description : {attribute.get('label')}{description}"
        content += "\n\n## References\n"
        for reference in model.get("references"):
            description = f"{reference.get('description')} {reference.get('documentation')}"
            description = f" - {description}" if description != " " else ""
            content += f"\n- {reference.get('name')}: {reference.get('label')}{description}.\n  Navigations:"
            referencing = reference.get("referencingEntity")
            referenced = reference.get("referencedEntity")
            content += "\n\t- From the parent entity '{parentEntity}' to the child entity '{childEntity}' using ANY/ALL with the '{roleName}' child role name. Parent to child reference is described as '{roleLabel} {description}'".format(
                parentEntity=referenced.get("name"),
                childEntity=referencing.get("name"),
                roleName=referencing.get("roleName"),
                roleLabel=referencing.get("roleLabel"),
                description=referencing.get("roleDocumentation")
            )
            content += "\n\t- From the child entity '{childEntity}' to the parent entity '{parentEntity}' using the '{roleName}.' parent role name. Child to parent relationship is described as '{roleLabel} {description}'".format(
                parentEntity=referenced.get("name"),
                childEntity=referencing.get("name"),
                roleName=referenced.get("roleName"),
                roleLabel=referenced.get("roleLabel"),
                description=referenced.get("roleDocumentation")
            )
        return content
