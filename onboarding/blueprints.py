"""Build current marketplace Blueprints without assuming runtime bindings."""

from __future__ import annotations

from typing import Any


def node_group(manifest: dict[str, Any]) -> dict[str, Any]:
    cluster = manifest["cluster"]
    bp = manifest["blueprint"]
    return {
        "id": bp["nodeGroupId"],
        "category": "worker",
        "displayName": bp["nodeGroupDisplayName"],
        "nodeCount": {
            "default": cluster["workerCountDefault"],
            "minimum": cluster["workerCountMinimum"],
        },
        "resources": {
            "minimum": {
                "cpu": str(cluster["minCpu"]),
                "memory": str(cluster["minMemory"]),
                "hasGPU": bool(cluster["hasGPU"]),
            },
            "hint": (
                f"Recommended: {cluster['recommendedCpu']} CPU and "
                f"{cluster['recommendedMemory']} memory per node."
            ),
        },
        "storage": {
            "disk": {
                "default": str(cluster["diskDefault"]),
                "minimum": str(cluster["diskMinimum"]),
            }
        },
    }


def add_instance(instances: list[dict], name: str, engine: str, version: str) -> None:
    if not name or not engine or not version:
        raise ValueError("Blueprint instances require name, engine and minimumVersion")
    entry = {"name": name, "engine": engine, "minimumVersion": str(version)}
    for existing in instances:
        if existing["name"] == name:
            if existing != entry:
                raise ValueError(f"Conflicting Blueprint instance: {name}")
            return
    instances.append(entry)


def add_explicit_dependencies(instances: list[dict], manifest: dict) -> None:
    for dep in manifest["dependencies"]["entries"]:
        if not dep.get("includeInBlueprint"):
            continue
        if dep["type"] == "auto":
            raise ValueError(f"Auto dependency {dep['name']} cannot be a Blueprint instance")
        if not dep.get("_instanceExplicit") or not dep.get("minimumVersion"):
            raise ValueError(
                f"Dependency {dep['name']} needs an explicit instance and minimumVersion "
                "when includeInBlueprint is true"
            )
        add_instance(instances, dep["instance"], dep["engine"], str(dep["minimumVersion"]))


def current_blueprint(
    *, name: str, owner: str, display_name: str, description: str,
    outcome: str, instances: list[dict], groups: list[dict], api_version: str,
) -> dict:
    if not instances:
        raise ValueError("Blueprint must contain at least one instance")
    if not groups:
        raise ValueError("Current Blueprint requires explicit node groups")
    group_ids = [group["id"] for group in groups]
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("Blueprint node group IDs must be unique")
    return {
        "apiVersion": api_version,
        "kind": "Blueprint",
        "metadata": {"name": name},
        "spec": {
            "owner": owner,
            "description": description,
            "outcome": outcome,
            "instances": instances,
            "hardwareTiers": [{"name": "default", "cluster": {"nodeGroups": groups}}],
            "ui": {"displayName": display_name},
        },
    }


def single_blueprint(manifest: dict) -> dict:
    bp = manifest["blueprint"]
    engine = manifest["engine"]
    instances: list[dict] = []
    add_explicit_dependencies(instances, manifest)
    add_instance(instances, bp["instanceName"], engine["name"], str(bp["minimumVersion"]))
    return current_blueprint(
        name=bp["name"], owner=manifest["partner"]["owner"],
        display_name=engine["displayName"], description=bp["description"],
        outcome=bp["outcome"], instances=instances, groups=[node_group(manifest)],
        api_version=manifest["apiVersion"],
    )
