#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const comfy = path.join(root, ".runtime", "ComfyUI");
const out = path.join(root, "production", "THE_LAST_RENDER", "workflows", "comfyui-api.json");

function walk(dir, acc = []) {
  if (!fs.existsSync(dir)) return acc;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (e.isFile() && e.name.endsWith(".json")) acc.push(p);
  }
  return acc;
}

function score(p) {
  const name = p.toLowerCase();
  let s = 0;
  if (name.includes("wan")) s += 1000;
  if (name.includes("2.1")) s += 100;
  if (name.includes("text")) s += 300;
  if (name.includes("t2v")) s += 300;
  if (name.includes("video")) s += 50;
  if (name.includes("image to video") || name.includes("i2v")) s -= 900;
  if (name.includes("flux") || name.includes("sdxl") || name.includes("image")) s -= 100;
  return s;
}

const files = walk(comfy).filter(p => /wan|text.to.video|t2v/i.test(p));
files.sort((a, b) => score(b) - score(a));

if (!files.length) {
  console.error("WAN_WORKFLOW_TEMPLATE_NOT_FOUND=true");
  process.exit(1);
}

const chosen = files[0];
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.copyFileSync(chosen, out);

console.log(`WAN_WORKFLOW_SELECTED=${chosen}`);
console.log(`WORKFLOW_WRITTEN=${out}`);
