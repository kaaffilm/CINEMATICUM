#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const workflowPath = process.env.WORKFLOW_JSON || "production/THE_LAST_RENDER/workflows/comfyui-api.json";
const comfyUrl = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

function die(msg) {
  console.error(msg);
  process.exit(1);
}

function readJson(p) {
  try { return JSON.parse(fs.readFileSync(p, "utf8")); }
  catch (e) { die(`WORKFLOW_JSON_READ_FAIL=${p}\n${e.message}`); }
}

function isApiWorkflow(j) {
  return j && typeof j === "object" && !Array.isArray(j) &&
    Object.values(j).length > 0 &&
    Object.values(j).every(v => v && typeof v === "object" && "class_type" in v && "inputs" in v);
}

function findGraph(j) {
  if (j?.nodes && Array.isArray(j.nodes)) return j;
  if (j?.workflow?.nodes && Array.isArray(j.workflow.nodes)) return j.workflow;
  if (j?.extra?.workflow?.nodes && Array.isArray(j.extra.workflow.nodes)) return j.extra.workflow;
  return null;
}

async function getObjectInfo() {
  const r = await fetch(`${comfyUrl}/object_info`);
  if (!r.ok) die(`COMFYUI_OBJECT_INFO_FAIL=${r.status}`);
  return await r.json();
}

function linkMap(graph) {
  const m = new Map();
  for (const l of graph.links || []) {
    if (Array.isArray(l)) {
      // [link_id, origin_node_id, origin_slot, target_node_id, target_slot, type]
      m.set(String(l[0]), [String(l[1]), Number(l[2])]);
    } else if (l && typeof l === "object") {
      m.set(String(l.id), [String(l.origin_id ?? l.source_id), Number(l.origin_slot ?? l.source_slot ?? 0)]);
    }
  }
  return m;
}

function inputNamesFromObjectInfo(info, classType) {
  const node = info[classType];
  const out = [];
  const sections = node?.input || {};
  for (const sec of ["required", "optional"]) {
    const obj = sections[sec] || {};
    for (const name of Object.keys(obj)) out.push(name);
  }
  return out;
}

function widgetValues(node) {
  const v = node.widgets_values;
  if (!v) return [];
  if (Array.isArray(v)) return v;
  if (typeof v === "object") return Object.values(v);
  return [];
}

async function main() {
  const raw = readJson(workflowPath);

  if (isApiWorkflow(raw)) {
    console.log("API_WORKFLOW_ALREADY_READY=true");
    console.log(`WORKFLOW_JSON=${workflowPath}`);
    return;
  }

  const graph = findGraph(raw);
  if (!graph) die("WORKFLOW_CONVERT_FAIL=true\nREASON=not_api_and_not_ui_graph");

  const info = await getObjectInfo();
  const links = linkMap(graph);
  const api = {};
  const missingClasses = new Set();

  for (const node of graph.nodes) {
    const id = String(node.id);
    const classType = node.type;
    if (!classType) continue;

    if (!info[classType]) missingClasses.add(classType);

    const inputs = {};

    for (const inp of node.inputs || []) {
      if (!inp || inp.link == null) continue;
      const src = links.get(String(inp.link));
      if (src) inputs[inp.name] = src;
    }

    const values = widgetValues(node);
    const names = inputNamesFromObjectInfo(info, classType).filter(n => !(n in inputs));

    for (let i = 0; i < Math.min(values.length, names.length); i++) {
      const val = values[i];
      if (val !== undefined && typeof val !== "object") inputs[names[i]] = val;
      else if (val !== undefined && val !== null && Array.isArray(val) === false) inputs[names[i]] = val;
    }

    api[id] = { class_type: classType, inputs };
  }

  if (missingClasses.size) {
    die(`WORKFLOW_CONVERT_FAIL=true\nREASON=missing_comfyui_node_classes\nMISSING_CLASSES=${[...missingClasses].join(",")}`);
  }

  fs.writeFileSync(workflowPath, JSON.stringify(api, null, 2) + "\n");
  console.log("UI_WORKFLOW_CONVERTED_TO_API=true");
  console.log(`WORKFLOW_JSON=${workflowPath}`);
  console.log(`API_NODE_COUNT=${Object.keys(api).length}`);
}

main().catch(e => die(`WORKFLOW_CONVERT_EXCEPTION=true\n${e.stack || e.message}`));
