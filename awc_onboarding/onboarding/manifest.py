"""Manifest normalization: turn raw wizard answers into a fully-expanded
render context used by the Jinja templates in ``templates/``.

This is intentionally the *only* place that knows how a slim answer set
turns into concrete resource names, catalog ids, and defaults -- keep the
templates themselves "dumb" (pure substitution).
"""

from __future__ import annotations

import copy
import re
from typing import Any

Manifest = dict[str, Any]


def _set(d: dict, key: str, value: Any) -> Any:
    """Like ``dict.setdefault``, but also overrides an *explicit* ``None``.

    ``fill_defaults()`` in questions.py marks unanswered optional questions
    with an explicit ``None`` (so one-shot input.yaml files don't have to
    spell out every optional field). Plain ``setdefault`` only kicks in when
    the key is entirely absent, so it would leave that ``None`` in place --
    this helper treats "absent" and "explicitly None" the same way.
    """
    if d.get(key) is None:
        d[key] = value
    return d[key]


def _slug(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "-").replace("_", "-")


def _parse_capability_fields(raw_fields: list[str]) -> list[dict[str, str]]:
    fields = []
    for item in raw_fields:
        if ":" in item:
            name, _, type_ = item.partition(":")
        else:
            name, type_ = item, "string"
        fields.append({"name": name.strip(), "type": type_.strip() or "string"})
    return fields


def normalize(answers: Manifest) -> Manifest:
    """Expand raw answers (as produced by the question graph) into the full
    manifest consumed by the generator. Mutates a deep copy; safe to call
    repeatedly (idempotent)."""

    m = copy.deepcopy(answers)

    partner = m.setdefault("partner", {})
    partner_id = _slug(partner.get("id"))
    if not partner_id:
        raise ValueError("partner.id is required")
    partner["id"] = partner_id
    _set(partner, "owner", partner_id.title())

    engine = m.setdefault("engine", {})
    _set(engine, "name", f"{partner_id}-ace-engine")
    _set(engine, "displayName", partner["owner"])
    _set(engine, "description", f"{engine['displayName']} on Cloudera Anywhere Cloud.")
    _set(engine, "template", "helm-simple")
    _set(engine, "version", m.get("helm", {}).get("version", "1.0.0"))

    helm = m.setdefault("helm", {})
    images = _normalize_images(m.get("images"), m.get("publish", {}))
    if images and helm.get("imageRepository") is None:
        # The first image is the primary one (referenced as .Image.<id> in the Engine).
        helm["imageRepository"] = images[0]["repository"]
        helm["imageTag"] = helm.get("imageTag") or images[0]["tag"]
    if engine["template"].startswith("helm"):
        _set(helm, "chart", partner_id)
        _set(helm, "chartId", _camel(helm["chart"]))
        _set(helm, "version", engine["version"])
    # Image coordinates always apply, even for native-k8s (which still pulls a
    # container image directly in its Deployment/StatefulSet spec).
    _set(helm, "imageRepository", partner_id)
    _set(helm, "imageTag", helm.get("imageTag") or helm.get("version") or engine["version"])
    _set(helm, "imageId", _camel(helm.get("imageRepository") or partner_id))

    if engine["template"] == "helm-multi-role":
        _set(
            engine,
            "roles",
            [
                {"name": "coordinator", "replicas": 1},
                {"name": "worker", "replicas": 2},
            ],
        )

    operator = m.setdefault("operator", {})
    if engine["template"] == "helm-operator":
        _set(operator, "chartId", _camel(operator.get("chartName") or partner_id))
        _set(operator, "namespace", "ace-operators")

    service = m.setdefault("service", {})
    _set(service, "port", 8080)
    _set(service, "hasLandingPage", True)
    _set(service, "landingPort", service["port"])

    capability = m.setdefault("capability", {})
    if capability.get("exportsStructuredData"):
        _set(capability, "name", f"{partner_id}-connection")
        raw_fields = capability.get("fields") or ["host:string", "port:integer"]
        if isinstance(raw_fields, str):
            raw_fields = [f.strip() for f in raw_fields.split(",") if f.strip()]
        capability["fields"] = _parse_capability_fields(raw_fields)

    dependencies = m.setdefault("dependencies", {})
    dep_list = dependencies.get("entries")
    if dep_list is None:
        if dependencies.get("hasAny"):
            dep_list = [
                {
                    "name": dependencies.get("name", "dep"),
                    "engine": dependencies.get("engine", ""),
                    "type": dependencies.get("type", "auto"),
                    "instance": dependencies.get("instance", ""),
                }
            ]
        else:
            dep_list = []
    for dep in dep_list:
        _set(dep, "type", "auto")
        # `instance` is the target's real Blueprint *instance* name (e.g.
        # "keycloak" / "dataspark-auth"). Only meaningful for optional/ref
        # deps -- Blueprint never lists "auto" deps (the operator wires those
        # privately inside the Engine itself, invisible to the Console).
        # Falls back to `engine` with the common "-engine" suffix stripped,
        # which matches this convention when you don't override it.
        if not dep.get("instance"):
            dep["instance"] = re.sub(r"-engine$", "", str(dep.get("engine", "")))
    dependencies["entries"] = dep_list

    blueprint = m.setdefault("blueprint", {})
    _set(blueprint, "needed", True)
    _set(blueprint, "name", partner_id)
    _set(blueprint, "outcome", engine["displayName"])
    _set(blueprint, "description", engine["description"])
    _set(blueprint, "instanceName", partner_id)
    _set(blueprint, "nodeGroupId", f"{partner_id}-nodes")
    _set(blueprint, "nodeGroupDisplayName", f"{engine['displayName']} Nodes")

    cluster = m.setdefault("cluster", {})
    _set(cluster, "kubernetesVersion", ">= 1.28.0")
    _set(cluster, "workerCountDefault", 1)
    _set(cluster, "workerCountMinimum", 1)
    _set(cluster, "minCpu", "4")
    _set(cluster, "minMemory", "16Gi")
    _set(cluster, "recommendedCpu", "8")
    _set(cluster, "recommendedMemory", "32Gi")
    _set(cluster, "diskDefault", "100Gi")
    _set(cluster, "diskMinimum", "50Gi")
    _set(cluster, "hasGPU", False)

    publish = m.setdefault("publish", {})
    _set(publish, "destinationRegistry", "<your-oci-registry.example.com>")
    _set(publish, "namespace", partner_id)

    mirror = m.setdefault("mirror", {})
    if engine["template"].startswith("helm") and not mirror.get("skip"):
        _set(mirror, "skip", False)
        mc = mirror.setdefault("chart", {})
        _set(mc, "repoUrl", helm.get("repoUrl"))
        _set(mc, "name", helm.get("chart"))
        _set(mc, "version", helm.get("version"))
        mi = mirror.setdefault("image", {})
        _set(mi, "repository", helm.get("imageRepository") or partner_id)
        _set(mi, "tag", helm.get("imageTag"))

    if not images:
        images = _normalize_images(
            [{"repository": helm["imageRepository"], "tag": helm["imageTag"]}], publish
        )
    m["images"] = images

    test = m.setdefault("test", {})
    _set(test, "landingUrl", "")

    img_suffix = f"images-{_version_slug(engine['version'])}"
    chart_suffix = f"charts-{_version_slug(helm.get('version', engine['version']))}"
    m["imageCatalogName"] = f"{blueprint['name']}-{img_suffix}"
    m["chartCatalogName"] = f"{blueprint['name']}-{chart_suffix}"
    m["rolePrefix"] = engine["name"]

    return m


def split_image_ref(ref: str) -> dict[str, str]:
    """'quay.io/org/app:1.2' -> {source, repository, tag}. A registry host is
    the first path segment when it contains '.' or ':' or is 'localhost'."""
    ref = str(ref).split("@", 1)[0]
    tag = "latest"
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        ref, tag = ref.rsplit(":", 1)
    parts = ref.split("/")
    source = "docker.io"
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        source, parts = parts[0], parts[1:]
    return {"source": source, "repository": "/".join(parts), "tag": tag}


def _normalize_images(raw: Any, publish: dict) -> list[dict]:
    """Each image: repository, tag, source registry (default docker.io), id.
    Accepts dicts or plain 'registry/repo:tag' strings."""
    out, seen = [], set()
    for item in raw or []:
        img = split_image_ref(item) if isinstance(item, str) else dict(item)
        if isinstance(item, dict) and "ref" in item:
            img = {**split_image_ref(item["ref"]), **{k: v for k, v in item.items() if k != "ref"}}
        img.setdefault("source", "docker.io")
        img.setdefault("tag", "latest")
        base = img.get("id") or _camel(img["repository"].rsplit("/", 1)[-1])
        img_id, n = base, 2
        while img_id in seen:
            img_id, n = f"{base}{n}", n + 1
        seen.add(img_id)
        img["id"] = img_id
        out.append(img)
    return out


def _camel(value: str) -> str:
    parts = [p for p in str(value).replace("/", "-").replace("_", "-").split("-") if p]
    if not parts:
        return "chart"
    return parts[0].lower() + "".join(p.title() for p in parts[1:])


def _version_slug(version: str) -> str:
    return str(version).replace(".", "-")
