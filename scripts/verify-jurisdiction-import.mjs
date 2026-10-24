#!/usr/bin/env node
import { readFileSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve, dirname, sep } from "node:path";
import { fileURLToPath } from "node:url";
const root=resolve(dirname(fileURLToPath(import.meta.url)),"..");
const m=JSON.parse(readFileSync(resolve(root,"JURISDICTION/SOURCE_IMPORT_MANIFEST.json"),"utf8"));
const errors=[];
const sha=(data)=>createHash("sha1").update(Buffer.from("blob "+data.length+"\0")).update(data).digest("hex");
if(m.schema!=="cinematicum.source-consolidation.v1"||m.source_commit!=="517fd51f43ae8a17db219da352f5b83998d45fbd"||m.files?.length!==39)errors.push("IMPORT_IDENTITY");
for(const item of m.files||[]){
 const abs=resolve(root,item.imported_path);
 if(!abs.startsWith(root+sep)||!item.imported_path.startsWith("JURISDICTION/")){errors.push("INVALID_PATH:"+item.source_path);continue}
 if(!existsSync(abs)){errors.push("MISSING:"+item.source_path);continue}
 const bytes=readFileSync(abs);
 if(bytes.length!==item.size||sha(bytes)!==item.blob_sha)errors.push("BYTE_DRIFT:"+item.source_path);
}
const status=JSON.parse(readFileSync(resolve(root,"JURISDICTION/CURRENT/CURRENT_CASE.json"),"utf8"));
if(status.current_status!=="CASE_OPEN_NOT_ISSUED")errors.push("ISSUANCE_OVERCLAIM");
const media=resolve(root,m.media_missing.path);
let mediaReady=false;
if(existsSync(media)){
 const bytes=readFileSync(media);
 mediaReady=bytes.length===m.media_missing.size && sha(bytes)===m.media_missing.sha1 &&
 createHash("sha256").update(bytes).digest("hex")===m.media_missing.sha256;
 if(!mediaReady)errors.push("MEDIA_HASH_MISMATCH");
}
if(process.argv.includes("--require-media")&&!mediaReady)errors.push("MEDIA_MISSING");
console.log(JSON.stringify({text_files:m.files.length,media_ready:mediaReady,case_status:status.current_status,errors},null,2));
if(errors.length)process.exitCode=1;
