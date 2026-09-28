"""
ModelXmlClient.py

Parses a Semarchy model edition export (the XML content returned by the
app-builder "Export model edition" REST API, DMClient.export_model_edition)
to expose MDM governance metadata that is not available through the xDM
App Builder REST API's `get-data-model` endpoint used by DMClient: enrichers,
validations, match rules, survivorship rules, publishers and LOV types.

The `get-data-model` endpoint only returns the logical model (entities,
attributes and references) needed to build SemQL queries. Rules that govern
data quality and consolidation (enrichers, validations, match rules,
survivorship rules) as well as reference data (publishers, LOV types) are
only present in the model edition export, so this client parses that content
instead. The export is always fetched live from the Semarchy repository via
DMClient; this class only parses the XML bytes/string it is given.
"""

import xml.etree.ElementTree as ET
from typing import Optional


def _val(el):
    """Extract the scalar value of a model XML element (as a 'val' attribute, a
    'null' marker, or plain text content)."""
    if el is None:
        return None
    if "val" in el.attrib:
        return el.attrib["val"]
    if el.attrib.get("null") == "true":
        return None
    return el.text


def _ref(el):
    """Return the internalID a model XML element refers to, if it is a reference."""
    return el.attrib.get("ref") if el is not None else None


def _is_true(value) -> bool:
    return value == "true"


class ModelXmlClient:
    """
    Provides governance metadata (enrichers, validations, match rules,
    survivorship rules, publishers, LOV types) parsed from a Semarchy model
    edition export.
    """

    def __init__(self):
        self._model = None
        self._by_internal_id = {}

    def load(self, xml_content):
        """
        Parses a model edition export (as returned by DMClient.export_model_edition)
        into memory, replacing any previously loaded model.

        Args:
            xml_content (bytes or str): The raw XML content of the model edition export.
        """
        root = ET.fromstring(xml_content)
        self._model = root.find("Model")
        self._by_internal_id = {}
        for el in self._model.iter():
            internal_id = _val(el.find("internalID"))
            if internal_id:
                self._by_internal_id[internal_id] = el

    def _resolve_ref(self, el):
        """Resolve an element that may only carry a 'ref' pointer into the referenced element."""
        if el is None:
            return None
        ref = _ref(el)
        return self._by_internal_id.get(ref) if ref else el

    def find_entity(self, entity_name: str):
        for entity in self._model.find("entities"):
            if _val(entity.find("name")) == entity_name:
                return entity
        return None

    def list_entity_names(self):
        return [_val(entity.find("name")) for entity in self._model.find("entities")]

    def get_enrichers(self, entity_name: str) -> Optional[list]:
        """
        Lists the enrichers (SemQL or plugin) configured on an entity, in
        execution order.
        """
        entity = self.find_entity(entity_name)
        if entity is None:
            return None
        container = entity.find("enrichers")
        enrichers = []
        for enricher in container if container is not None else []:
            enrichers.append({
                "name": _val(enricher.find("name")),
                "label": _val(enricher.find("label")),
                "type": enricher.tag,
                "description": _val(enricher.find("description")),
                "condition": _val(enricher.find("condition")),
                "executionScope": _val(enricher.find("enricherExecutionScope")),
                "posInEntity": int(_val(enricher.find("posInEntity")) or 0),
            })
        enrichers.sort(key=lambda e: e["posInEntity"])
        return enrichers

    def get_validations(self, entity_name: str) -> Optional[dict]:
        """
        Lists the validations configured on an entity: mandatory attributes,
        LOV-validated attributes, unique keys and row check constraints.
        """
        entity = self.find_entity(entity_name)
        if entity is None:
            return None

        mandatory_attributes = []
        lov_validated_attributes = []
        for container_name in ("PKAttributes", "atomicAttributes", "complexAttributes"):
            container = entity.find(container_name)
            for attr in container if container is not None else []:
                name = _val(attr.find("name"))
                if _is_true(_val(attr.find("mandatory"))):
                    mandatory_attributes.append({
                        "name": name,
                        "scope": _val(attr.find("mandatoryValidationScope")),
                        "label": _val(attr.find("mandatoryValidationLabel")),
                    })
                lov_type = self._resolve_ref(attr.find("abstractAtomicType"))
                if lov_type is not None and lov_type.tag == "LOVType":
                    lov_validated_attributes.append({
                        "name": name,
                        "lovType": _val(lov_type.find("name")),
                        "scope": _val(attr.find("LOVValidationScope")),
                    })

        unique_keys = []
        container = entity.find("uniqueKeys")
        for uk in container if container is not None else []:
            attributes_container = uk.find("attributes")
            attribute_names = []
            for attr_ref in attributes_container if attributes_container is not None else []:
                resolved = self._resolve_ref(attr_ref)
                attribute_names.append(_val(resolved.find("name")) if resolved is not None else None)
            unique_keys.append({
                "name": _val(uk.find("name")),
                "label": _val(uk.find("label")),
                "attributes": attribute_names,
            })

        row_check_constraints = []
        container = entity.find("abstractRowCheckConstraints")
        for rc in container if container is not None else []:
            row_check_constraints.append({
                "name": _val(rc.find("name")),
                "label": _val(rc.find("label")),
                "validator": _val(rc.find("validator")),
                "brokenValidationLabel": _val(rc.find("brokenValidationLabel")),
            })

        return {
            "mandatoryAttributes": mandatory_attributes,
            "lovValidatedAttributes": lov_validated_attributes,
            "uniqueKeys": unique_keys,
            "rowCheckConstraints": row_check_constraints,
        }

    def get_match_rules(self, entity_name: str) -> Optional[dict]:
        """
        Lists the matcher configuration and match rules (duplicate detection
        conditions) configured on an entity.
        """
        entity = self.find_entity(entity_name)
        if entity is None:
            return None

        matcher_container = entity.find("matcher")
        matcher_elements = list(matcher_container) if matcher_container is not None else []
        if not matcher_elements:
            return {"matcher": None, "rules": []}

        matcher = matcher_elements[0]
        matcher_info = {
            "autoConfirmGoldenThreshold": _val(matcher.find("autoConfirmGoldenThreshold")),
            "autoConfirmSingletons": _val(matcher.find("autoConfirmSingletons")),
            "mergeThresholdNewGroup": _val(matcher.find("mergeThresholdNewGroup")),
            "mergeThresholdMergingUnconfirmed": _val(matcher.find("mergeThresholdMergingUnconfirmed")),
            "mergeThresholdMergingConfirmed": _val(matcher.find("mergeThresholdMergingConfirmed")),
            "useTransitiveMatchScore": _val(matcher.find("useTransitiveMatchScore")),
        }

        rules = []
        match_rules_container = matcher.find("matchRules")
        for rule in match_rules_container if match_rules_container is not None else []:
            rules.append({
                "name": _val(rule.find("name")),
                "label": _val(rule.find("label")),
                "matchScore": int(_val(rule.find("matchScore")) or 0),
                "condition": _val(rule.find("condition")),
                "usingMatchOn": _is_true(_val(rule.find("usingMatchOn"))),
                "matchOnExpression": _val(rule.find("matchOnExpression")),
                "posInParent": int(_val(rule.find("posInParent")) or 0),
            })
        rules.sort(key=lambda r: r["posInParent"])

        return {"matcher": matcher_info, "rules": rules}

    def get_survivorship_rules(self, entity_name: str) -> Optional[list]:
        """
        Lists the survivorship rules configured on an entity, describing how
        golden record attributes are consolidated from master records.
        """
        entity = self.find_entity(entity_name)
        if entity is None:
            return None

        rules = []
        container = entity.find("survivorshipRules")
        for rule in container if container is not None else []:
            rankings = []
            rankings_container = rule.find("publisherRankings")
            for ranking in rankings_container if rankings_container is not None else []:
                publisher = self._resolve_ref(ranking.find("publisher"))
                rankings.append({
                    "rank": int(_val(ranking.find("rank")) or 0),
                    "publisher": _val(publisher.find("name")) if publisher is not None else None,
                })
            rankings.sort(key=lambda r: r["rank"])

            rules.append({
                "name": _val(rule.find("name")),
                "label": _val(rule.find("label")),
                "type": rule.tag,
                "defaultRule": _is_true(_val(rule.find("defaultRule"))),
                "consolidationStrategy": _val(rule.find("consolidationStrategy")),
                "consolidationOrderByExpression": _val(rule.find("consolidationOrderByExpression")),
                "consolidationSkipNulls": _is_true(_val(rule.find("consolidationSkipNulls"))),
                "publisherRankings": rankings,
            })
        return rules

    def list_publishers(self) -> list:
        """Lists the publishers (data source systems) defined in the model."""
        container = self._model.find("publishers")
        publishers = []
        for pub in container if container is not None else []:
            publishers.append({
                "name": _val(pub.find("name")),
                "label": _val(pub.find("label")),
                "code": _val(pub.find("code")),
                "active": _is_true(_val(pub.find("active"))),
                "description": _val(pub.find("description")),
            })
        return publishers

    def list_lov_types(self) -> list:
        """Lists the List-Of-Values (LOV) types defined in the model, with their allowed values."""
        container = self._model.find("LOVTypes")
        lov_types = []
        for lov in container if container is not None else []:
            values = []
            values_container = lov.find("LOVValues")
            for value in values_container if values_container is not None else []:
                values.append({
                    "code": _val(value.find("code")),
                    "label": _val(value.find("label")),
                    "description": _val(value.find("description")),
                })
            lov_types.append({
                "name": _val(lov.find("name")),
                "label": _val(lov.find("label")),
                "description": _val(lov.find("description")),
                "values": values,
            })
        return lov_types

    # ---- Prompt formatting ----

    def enrichers_to_prompt(self, entity_name: str) -> str:
        enrichers = self.get_enrichers(entity_name)
        if enrichers is None:
            return f"Entity '{entity_name}' not found in the model."
        if not enrichers:
            return f"# Enrichers for '{entity_name}'\n\nNo enrichers are configured for this entity."
        content = f"# Enrichers for '{entity_name}'\n"
        for enricher in enrichers:
            content += f"\n- name: {enricher['name']}\n  label: {enricher['label']}\n  type: {enricher['type']}\n  executionScope: {enricher['executionScope']}"
            if enricher["condition"]:
                content += f"\n  condition: {enricher['condition']}"
            if enricher["description"]:
                content += f"\n  description: {enricher['description']}"
        return content

    def validations_to_prompt(self, entity_name: str) -> str:
        validations = self.get_validations(entity_name)
        if validations is None:
            return f"Entity '{entity_name}' not found in the model."
        content = f"# Validations for '{entity_name}'\n"

        content += "\n## Mandatory Attributes\n"
        if validations["mandatoryAttributes"]:
            for attr in validations["mandatoryAttributes"]:
                content += f"- {attr['name']} (scope: {attr['scope']})\n"
        else:
            content += "None.\n"

        content += "\n## LOV-Validated Attributes\n"
        if validations["lovValidatedAttributes"]:
            for attr in validations["lovValidatedAttributes"]:
                content += f"- {attr['name']} -> LOV type '{attr['lovType']}' (scope: {attr['scope']})\n"
        else:
            content += "None.\n"

        content += "\n## Unique Keys\n"
        if validations["uniqueKeys"]:
            for uk in validations["uniqueKeys"]:
                content += f"- {uk['name']}: {', '.join(a for a in uk['attributes'] if a)}\n"
        else:
            content += "None.\n"

        content += "\n## Row Check Constraints\n"
        if validations["rowCheckConstraints"]:
            for rc in validations["rowCheckConstraints"]:
                content += f"- {rc['name']}: {rc['validator']} (error message: {rc['brokenValidationLabel']})\n"
        else:
            content += "None.\n"

        return content

    def match_rules_to_prompt(self, entity_name: str) -> str:
        match_rules = self.get_match_rules(entity_name)
        if match_rules is None:
            return f"Entity '{entity_name}' not found in the model."
        content = f"# Match Rules for '{entity_name}'\n"
        matcher = match_rules["matcher"]
        if matcher is None:
            content += "\nNo matcher is configured for this entity."
            return content

        content += "\n## Matcher Configuration\n"
        content += f"- Auto-confirm golden threshold: {matcher['autoConfirmGoldenThreshold']}\n"
        content += f"- Auto-confirm singletons: {matcher['autoConfirmSingletons']}\n"
        content += f"- Merge threshold (new group): {matcher['mergeThresholdNewGroup']}\n"
        content += f"- Merge threshold (merging unconfirmed): {matcher['mergeThresholdMergingUnconfirmed']}\n"
        content += f"- Merge threshold (merging confirmed): {matcher['mergeThresholdMergingConfirmed']}\n"

        content += "\n## Match Rules (evaluated in order, higher score first)\n"
        if match_rules["rules"]:
            for rule in match_rules["rules"]:
                content += f"\n- name: {rule['name']}\n  label: {rule['label']}\n  matchScore: {rule['matchScore']}\n  condition: {rule['condition']}"
        else:
            content += "None.\n"
        return content

    def survivorship_rules_to_prompt(self, entity_name: str) -> str:
        rules = self.get_survivorship_rules(entity_name)
        if rules is None:
            return f"Entity '{entity_name}' not found in the model."
        if not rules:
            return f"# Survivorship Rules for '{entity_name}'\n\nNo survivorship rules are configured for this entity."
        content = f"# Survivorship Rules for '{entity_name}'\n"
        for rule in rules:
            content += f"\n- name: {rule['name']}\n  label: {rule['label']}\n  type: {rule['type']}\n  defaultRule: {rule['defaultRule']}\n  consolidationStrategy: {rule['consolidationStrategy']}"
            if rule["consolidationOrderByExpression"]:
                content += f"\n  consolidationOrderByExpression: {rule['consolidationOrderByExpression']}"
            content += f"\n  consolidationSkipNulls: {rule['consolidationSkipNulls']}"
            if rule["publisherRankings"]:
                content += "\n  publisherRankings (most trusted first):"
                for ranking in rule["publisherRankings"]:
                    content += f"\n    {ranking['rank']}. {ranking['publisher']}"
        return content

    def publishers_to_prompt(self) -> str:
        publishers = self.list_publishers()
        if not publishers:
            return "No publishers are defined in the model."
        content = "# Publishers\n"
        for pub in publishers:
            content += f"\n- name: {pub['name']}\n  label: {pub['label']}\n  code: {pub['code']}\n  active: {pub['active']}"
            if pub["description"]:
                content += f"\n  description: {pub['description']}"
        return content

    def lov_types_to_prompt(self) -> str:
        lov_types = self.list_lov_types()
        if not lov_types:
            return "No LOV types are defined in the model."
        content = "# LOV Types\n"
        for lov in lov_types:
            content += f"\n- name: {lov['name']}\n  label: {lov['label']}\n  values:"
            for value in lov["values"]:
                content += f"\n    - code: {value['code']}, label: {value['label']}"
        return content
