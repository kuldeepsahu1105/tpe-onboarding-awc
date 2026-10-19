/* global JSONEditor, jsyaml */

const YAML_SNIPPET_KEYS = [
  ["providesYaml", "provides"],
  ["configSchemaYaml", "configSchema"],
  ["healthChecksYaml", "healthChecks"],
  ["capabilitiesYaml", "capabilities"],
];

function stripEmpty(obj) {
  if (obj === null || typeof obj !== "object") return obj;
  if (Array.isArray(obj)) {
    return obj.map(stripEmpty).filter((v) => v !== undefined);
  }
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === "") continue;
    if (typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0) continue;
    out[k] = stripEmpty(v);
  }
  return out;
}

function mergeYamlSnippets(doc) {
  const merged = { ...doc };
  for (const [yamlKey, targetKey] of YAML_SNIPPET_KEYS) {
    const raw = merged[yamlKey];
    delete merged[yamlKey];
    if (!raw || !String(raw).trim()) continue;
    try {
      merged[targetKey] = jsyaml.load(String(raw));
    } catch (err) {
      throw new Error(`${yamlKey}: ${err.message}`);
    }
  }
  return merged;
}

function documentToYaml(editorValue) {
  const doc = stripEmpty(mergeYamlSnippets(editorValue));
  if (doc.version !== "v1") {
    doc.version = "v1";
  }
  return jsyaml.dump(doc, { lineWidth: 120, noRefs: true });
}

function yamlToStartValue(yamlText) {
  const doc = jsyaml.load(yamlText);
  const start = { ...doc };
  for (const [yamlKey, targetKey] of YAML_SNIPPET_KEYS) {
    if (start[targetKey] !== undefined) {
      start[yamlKey] = jsyaml.dump(start[targetKey], { lineWidth: 120, noRefs: true }).trimEnd();
      delete start[targetKey];
    }
  }
  return start;
}

function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function download(filename, text) {
  const blob = new Blob([text], { type: "text/yaml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function suggestMakeCommand(directory) {
  const formPath = directory ? `${directory}.input_form.yaml` : "my-engine.input_form.yaml";
  return `make scaffold-engine FORM=${formPath} FORCE=1`;
}

async function loadDefaultStartVal() {
  try {
    const res = await fetch("../input_form.minimal.example.yaml");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return yamlToStartValue(await res.text());
  } catch {
    return {
      version: "v1",
      directory: "my-service",
      engine: {
        name: "my-service-engine",
        displayName: "My Service",
        description: "Short description.",
      },
      imageCatalog: {
        name: "my-service-images-1-0-0",
        images: [
          {
            id: "myService",
            registry: "docker-private.infra.cloudera.com",
            repository: "cloudera_thirdparty/hardened/my-service",
            tag: "1.0.0-r0-202601010000",
          },
        ],
      },
      chartCatalog: {
        name: "my-service-charts-1-0-0",
        charts: [
          {
            id: "myService",
            registry: "docker-private.infra.cloudera.com",
            repository: "cloudera-thirdparty-helm/my-service",
            version: "1.0.0",
          },
        ],
      },
      helm: {
        chartID: "myService",
        values:
          'fullnameOverride: {{ .Metadata.Name | quote }}\nimage:\n  registry: {{ .Image.myService.registry | quote }}\n',
      },
      rbac: { preset: "helm-basic" },
      blueprint: { enabled: true, minimumVersion: "1.0.0" },
    };
  }
}

let editor;

async function init() {
  const schemaRes = await fetch("./input_form.ui.schema.json");
  const schema = await schemaRes.json();
  const startval = await loadDefaultStartVal();

  editor = new JSONEditor(document.getElementById("form-root"), {
    schema,
    startval,
    theme: "html",
    disable_edit_json: false,
    disable_properties: false,
    show_opt_in: true,
    prompt_before_delete: true,
  });

  document.getElementById("btn-export").addEventListener("click", () => {
    try {
      const errors = editor.validate();
      if (errors.length) {
        setStatus(`Fix ${errors.length} validation error(s) in the form.`, true);
        return;
      }
      const yaml = documentToYaml(editor.getValue());
      document.getElementById("yaml-output").value = yaml;
      const dir = editor.getValue().directory || "engine";
      document.getElementById("make-cmd").textContent = suggestMakeCommand(dir);
      setStatus("YAML updated. Download or copy, then run make scaffold-engine.");
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById("btn-download").addEventListener("click", () => {
    const out = document.getElementById("yaml-output").value;
    if (!out.trim()) {
      setStatus("Export YAML first.", true);
      return;
    }
    const dir = editor.getValue().directory || "engine";
    download(`${dir}.input_form.yaml`, out);
    setStatus(`Downloaded ${dir}.input_form.yaml`);
  });

  document.getElementById("btn-load-yaml").addEventListener("click", () => {
    const raw = document.getElementById("yaml-output").value;
    if (!raw.trim()) {
      setStatus("Paste YAML in the output panel first.", true);
      return;
    }
    try {
      editor.setValue(yamlToStartValue(raw));
      setStatus("Loaded YAML into the form.");
    } catch (err) {
      setStatus(`Parse error: ${err.message}`, true);
    }
  });

  document.getElementById("file-import").addEventListener("change", async (ev) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      editor.setValue(yamlToStartValue(text));
      document.getElementById("yaml-output").value = text;
      setStatus(`Imported ${file.name}`);
    } catch (err) {
      setStatus(`Import failed: ${err.message}`, true);
    }
    ev.target.value = "";
  });
}

init().catch((err) => setStatus(err.message, true));
