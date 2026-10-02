"""The onboarding question graph.

This module defines every question the wizard (CLI or MCP) can ask a
partner/engine owner. Questions are declarative so the exact same graph can
drive:

* an interactive terminal wizard (``onboarding/wizard.py``)
* a one-shot answers file (``--answers answers.yaml``)
* the MCP server, where an AI agent asks the questions conversationally and
  calls ``submit_answer`` for each one (``mcp_server/server.py``)

Each :class:`Question` knows:

* ``id``            - dotted path into the manifest it fills in
* ``prompt``        - the human-readable question text
* ``help``          - one or two sentences of extra context (shown on ``?``)
* ``kind``          - "text" | "int" | "bool" | "choice" | "list"
* ``choices``       - allowed values for "choice" questions
* ``default``       - pre-filled default (can reference earlier answers)
* ``required``      - whether an empty answer is rejected
* ``when``          - predicate over the answers-so-far; question is skipped
                       if it returns False

The question set mirrors the Anywhere Cloud Ecosystem concepts directly:
Capability, ClusterRequirements, Engine (+ versionCatalog, configSchema,
provides, dependencies, healthChecks), Operator, Blueprint, ChartCatalog,
ImageCatalog and RBAC -- see ``docs/AWC_CONCEPTS.md`` for the full mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

Answers = dict[str, Any]

_SENTINEL = object()


@dataclass
TEMPLATE_HELP = """Not sure? Answer in order, stop at the first YES:
 1. Does the app have NO Helm chart (you only have plain Kubernetes YAML)?  -> native-k8s
 2. Do you install an Operator first, then create a custom resource (CR)?   -> helm-operator
 3. Does one chart run several DIFFERENT kinds of pods (e.g. FE + BE)?      -> helm-multi-role
 4. Otherwise (one chart, one kind of workload)                             -> helm-simple

Real-world examples
 helm-simple      Neo4j (single server), Grafana, Redis, MinIO, Superset, a REST API service.
                  Pods are all alike; you scale by replica count.
 helm-multi-role  StarRocks (FE + BE), PuppyGraph (controlplane/leader/compute), Trino
                  (coordinator + workers), Druid, Pinot, Kafka+ZooKeeper-style charts.
                  Each role needs its own replicas / CPU / memory / disk.
 helm-operator    PostgreSQL via CloudNativePG, Kafka via Strimzi, Flink via Flink Operator,
                  Spark via Spark Operator, Elasticsearch via ECK, PhoenixAI-style operators.
                  Signs: chart installs CRDs; docs say 'kubectl apply -f my-cluster.yaml'.
 native-k8s       An in-house tool with only Deployment/Service YAML, a small internal
                  service, a proof of concept with no chart published yet.

Quick tips: if values.yaml has sections like 'fe:' and 'be:' it is multi-role. If the install
guide has two steps (install operator, then apply a CR) it is operator. When unsure, pick
helm-simple; you can switch later by changing one line. Full guide: docs/CHOOSING_A_TEMPLATE.md"""


class Question:
    id: str
    prompt: str
    kind: str = "text"  # text | int | bool | choice | list
    help: str = ""
    choices: Optional[list[str]] = None
    default: Optional[Any] = None
    required: bool = True
    when: Optional[Callable[[Answers], bool]] = None

    def is_applicable(self, answers: Answers) -> bool:
        return self.when is None or self.when(answers)

    def resolved_default(self, answers: Answers) -> Any:
        if callable(self.default):
            return self.default(answers)
        return self.default


def _get(answers: Answers, dotted: str, fallback: Any = None) -> Any:
    cur: Any = answers
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return fallback
        cur = cur[part]
    return cur


def _slug(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "-").replace("_", "-")


def _default_recommended_cpu(a: Answers) -> str:
    min_cpu = _get(a, "cluster.minCpu", "4")
    return str(int(min_cpu) * 2) if str(min_cpu).isdigit() else "8"


# ---------------------------------------------------------------------------
# The question graph, in interview order.
# ---------------------------------------------------------------------------
QUESTIONS: list[Question] = [
    # --- Identity -----------------------------------------------------
    Question(
        id="partner.id",
        prompt="What is a short, unique slug id for this engine/partner? "
        "(lowercase, hyphens, no spaces -- e.g. 'starrocks', 'neo4j', 'dataspark')",
        help="Used as the directory name and prefix for every generated resource name.",
    ),
    Question(
        id="partner.owner",
        prompt="What is the vendor/owner display name? (e.g. 'StarRocks', 'Neo4j, Inc.')",
        default=lambda a: _slug(_get(a, "partner.id")).title(),
    ),
    Question(
        id="engine.displayName",
        prompt="What should the Marketplace tile display name be?",
        default=lambda a: f"{_get(a, 'partner.owner')}",
    ),
    Question(
        id="engine.description",
        prompt="One or two sentences describing what this engine does, for the Marketplace listing.",
    ),
    # --- Shape of the deployment ---------------------------------------
    Question(
        id="engine.template",
        prompt="How does this engine ship?",
        kind="choice",
        choices=["helm-simple", "helm-multi-role", "helm-operator", "native-k8s"],
        help=TEMPLATE_HELP,
        default="helm-simple",
    ),
    # --- Helm coordinates (helm-*) --------------------------------------
    Question(
        id="helm.repoUrl",
        prompt="Upstream Helm repository URL (or 'oci://...' for an OCI chart repo)?",
        when=lambda a: _get(a, "engine.template", "").startswith("helm"),
    ),
    Question(
        id="helm.chart",
        prompt="Upstream Helm chart name?",
        when=lambda a: _get(a, "engine.template", "").startswith("helm"),
        default=lambda a: _get(a, "partner.id"),
    ),
    Question(
        id="helm.version",
        prompt="Upstream Helm chart version to pin?",
        when=lambda a: _get(a, "engine.template", "").startswith("helm"),
    ),
    Question(
        id="helm.imageRepository",
        prompt="Primary container image repository (e.g. 'neo4j' or 'starrocks/fe-ubuntu')?",
        when=lambda a: _get(a, "engine.template", "").startswith("helm"),
        required=False,
    ),
    Question(
        id="helm.imageTag",
        prompt="Primary container image tag?",
        when=lambda a: _get(a, "engine.template", "").startswith("helm"),
        default=lambda a: _get(a, "helm.version"),
        required=False,
    ),
    # --- Operator-specific (helm-operator) ------------------------------
    Question(
        id="operator.chartRepoUrl",
        prompt="Operator Helm chart repository (e.g. 'oci://ghcr.io/cloudnative-pg/charts')?",
        when=lambda a: _get(a, "engine.template") == "helm-operator",
    ),
    Question(
        id="operator.chartName",
        prompt="Operator Helm chart name?",
        when=lambda a: _get(a, "engine.template") == "helm-operator",
    ),
    Question(
        id="operator.chartVersion",
        prompt="Operator Helm chart version?",
        when=lambda a: _get(a, "engine.template") == "helm-operator",
    ),
    Question(
        id="operator.namespace",
        prompt="Target namespace for the operator install (must already exist on the cluster)?",
        when=lambda a: _get(a, "engine.template") == "helm-operator",
        default="ace-operators",
    ),
    # --- Networking / UX -------------------------------------------------
    Question(
        id="service.port",
        prompt="Primary service port the engine listens on?",
        kind="int",
        default=8080,
    ),
    Question(
        id="service.hasLandingPage",
        prompt="Does this engine expose a web UI end users should click into from the Marketplace?",
        kind="bool",
        default=True,
    ),
    Question(
        id="service.landingPort",
        prompt="Which port serves that web UI?",
        kind="int",
        default=lambda a: _get(a, "service.port"),
        when=lambda a: _get(a, "service.hasLandingPage") is True,
    ),
    # --- Capability (typed export contract) ------------------------------
    Question(
        id="capability.exportsStructuredData",
        prompt=(
            "Will OTHER engines need to consume structured connection data from this one "
            "(host/port/credentials) via `.Dependencies.<name>.*` in their templates? "
            "(Answer 'No' if you only expose a Secret/ConfigMap by reference, or nothing at all.)"
        ),
        kind="bool",
        default=False,
    ),
    Question(
        id="capability.name",
        prompt="Name for the Capability contract (e.g. 'dataspark-db-connection')?",
        when=lambda a: _get(a, "capability.exportsStructuredData") is True,
        default=lambda a: f"{_get(a, 'partner.id')}-connection",
    ),
    Question(
        id="capability.fields",
        prompt=(
            "List the fields of that contract as 'name:type' pairs, comma-separated "
            "(e.g. 'host:string, port:integer, database:string, credentialsSecret:string')."
        ),
        kind="list",
        when=lambda a: _get(a, "capability.exportsStructuredData") is True,
        default="host:string, port:integer",
    ),
    # --- Dependencies on other engines ------------------------------------
    # One engine is onboarded per session, but it can still interoperate with
    # ANY other Engine already present in the cluster -- one of your own
    # previously-onboarded engines, a Cloudera-native engine, or another
    # partner's/third-party/open-source engine. The actual list of dependency
    # entries (name/engine/type) is collected as a repeatable loop by the
    # wizard (see ``wizard._collect_dependencies``) and by the MCP server's
    # ``add_dependency``/``finish_dependencies`` tools -- not as fixed
    # questions here -- so there is no cap on how many an engine can declare.
    # A one-shot answers file can set ``dependencies.entries`` directly, e.g.:
    #   dependencies:
    #     hasAny: true
    #     entries:
    #       - {name: db, engine: postgres-engine, type: auto}
    #       - {name: auth, engine: keycloak-engine, type: optional}
    Question(
        id="dependencies.hasAny",
        prompt=(
            "Does this engine depend on, or integrate with, any OTHER engine already "
            "registered on this AWC cluster? This can be one of its own private "
            "components (e.g. a bundled database), a Cloudera-native engine, or a "
            "separate/external third-party engine someone else onboarded."
        ),
        kind="bool",
        default=False,
    ),
    # --- Multi-component / Blueprint ---------------------------------------
    Question(
        id="blueprint.needed",
        prompt=(
            "Should this appear as a deployable tile in the Anywhere Cloud Console Marketplace? "
            "(Required unless this is a hidden/internal dependency engine only.)"
        ),
        kind="bool",
        default=True,
    ),
    Question(
        id="blueprint.outcome",
        prompt="Short outcome/tagline shown on the Marketplace tile (e.g. 'Graph database', 'OLAP analytics')?",
        when=lambda a: _get(a, "blueprint.needed") is True,
    ),
    # --- Cluster sizing (ClusterRequirements / Blueprint.cluster) ----------
    Question(
        id="cluster.kubernetesVersion",
        prompt="Minimum supported Kubernetes version constraint (e.g. '>= 1.24.0')?",
        default=">= 1.28.0",
    ),
    Question(
        id="cluster.workerCountDefault",
        prompt="Default number of worker nodes?",
        kind="int",
        default=1,
    ),
    Question(
        id="cluster.workerCountMinimum",
        prompt="Minimum number of worker nodes?",
        kind="int",
        default=1,
    ),
    Question(
        id="cluster.minCpu",
        prompt="Minimum CPU cores per worker node?",
        default="4",
    ),
    Question(
        id="cluster.minMemory",
        prompt="Minimum memory per worker node (e.g. '16Gi')?",
        default="16Gi",
    ),
    Question(
        id="cluster.recommendedCpu",
        prompt="Recommended CPU cores per worker node?",
        default=_default_recommended_cpu,
    ),
    Question(
        id="cluster.recommendedMemory",
        prompt="Recommended memory per worker node?",
        default="32Gi",
    ),
    Question(
        id="cluster.diskDefault",
        prompt="Default root/data disk size per node (e.g. '100Gi')?",
        default="100Gi",
    ),
    Question(
        id="cluster.diskMinimum",
        prompt="Minimum disk size per node?",
        default="50Gi",
    ),
    Question(
        id="cluster.hasGPU",
        prompt="Does this engine require GPU nodes?",
        kind="bool",
        default=False,
    ),
    # --- Publish target -----------------------------------------------------
    Question(
        id="publish.destinationRegistry",
        prompt="OCI registry hostname charts/images will be mirrored to and published from?",
        default="<your-oci-registry.example.com>",
    ),
    Question(
        id="publish.namespace",
        prompt="Registry namespace/path prefix for this engine's artifacts?",
        default=lambda a: _get(a, "partner.id"),
    ),
    Question(
        id="mirror.skip",
        prompt="Are the chart and image ALREADY present in that registry (skip mirroring)?",
        kind="bool",
        default=False,
        when=lambda a: _get(a, "engine.template", "").startswith("helm"),
    ),
]


def question_by_id(qid: str) -> Optional[Question]:
    for q in QUESTIONS:
        if q.id == qid:
            return q
    return None


def applicable_questions(answers: Answers) -> list[Question]:
    """Return the questions that still apply given the answers so far."""
    return [q for q in QUESTIONS if q.is_applicable(answers)]


def fill_defaults(answers: Answers) -> Answers:
    """Fill in every currently-unanswered, applicable question's resolved
    default, in place. Lets a one-shot ``input.yaml`` (like a slim
    ``partner.yaml``) specify only the fields the partner actually cares
    about -- everything else falls back exactly like the interactive wizard
    would. Loops to a fixed point since later defaults/``when`` predicates
    can depend on earlier (just-defaulted) answers."""
    changed = True
    while changed:
        changed = False
        for question in applicable_questions(answers):
            if _get(answers, question.id, _SENTINEL) is not _SENTINEL:
                continue
            default = question.resolved_default(answers)
            if default is None:
                if question.required:
                    continue  # genuinely missing -- surfaced by next_question()
                # Optional with nothing to default to (e.g. helm.imageRepository):
                # explicitly mark it "answered" with None so a one-shot input.yaml
                # isn't forced to spell out every optional field.
                set_answer(answers, question.id, None)
                changed = True
                continue
            set_answer(answers, question.id, coerce(question, default))
            changed = True
    return answers


def next_question(answers: Answers) -> Optional[Question]:
    """Return the next unanswered, applicable question, or None if done."""
    for q in QUESTIONS:
        if not q.is_applicable(answers):
            continue
        if _get(answers, q.id, _SENTINEL) is _SENTINEL:
            return q
    return None


def set_answer(answers: Answers, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = answers
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def coerce(question: Question, raw: Any) -> Any:
    """Coerce a raw (likely string) answer into the question's declared kind."""
    if raw is None:
        return None
    if question.kind == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"y", "yes", "true", "1"}
    if question.kind == "int":
        if isinstance(raw, int):
            return raw
        return int(str(raw).strip())
    if question.kind == "list":
        if isinstance(raw, list):
            return raw
        return [item.strip() for item in str(raw).split(",") if item.strip()]
    return raw
