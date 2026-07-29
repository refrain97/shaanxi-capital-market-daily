#!/usr/bin/env node

/* Upload exactly one V2-owned daily PNG to IMA.
 *
 * The caller owns retry state.  This adapter never invents a duplicate
 * filename: an exact IMA hit is reconciled as success; another repeated-name
 * response is returned for manual review.  Credentials stay in the official
 * IMA skill's configured client files and are never written here.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const skillRoot = process.env.IMA_SKILL_ROOT || path.join(os.homedir(), ".codex", "skills", "ima-skill");
const imaApiPath = path.join(skillRoot, "ima_api.cjs");
const preflightPath = path.join(skillRoot, "knowledge-base", "scripts", "preflight-check.cjs");
const cosUploadPath = path.join(skillRoot, "knowledge-base", "scripts", "cos-upload.cjs");

function parseArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length;) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key || !key.startsWith("--") || value === undefined) throw new Error(`参数错误：${key || "末尾"}`);
    args[key.slice(2)] = value;
    index += 2;
  }
  for (const key of ["file", "name", "kb"]) if (!args[key]) throw new Error(`缺少 --${key}`);
  return args;
}

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", maxBuffer: 4 * 1024 * 1024 });
  if (result.status !== 0) throw new Error(`${path.basename(command)} 执行失败：${String(result.stderr || result.stdout || "").trim().slice(0, 500)}`);
  return String(result.stdout || "").trim();
}

function api(apiPath, body) {
  const raw = run("node", [imaApiPath, apiPath, JSON.stringify(body)]);
  const response = JSON.parse(raw || "{}");
  if (response.code !== 0) throw new Error(`IMA ${apiPath} 调用失败：${String(response.msg || response.code)}`);
  return response;
}

function values(value, found = []) {
  if (typeof value === "string") found.push(value);
  else if (Array.isArray(value)) value.forEach(item => values(item, found));
  else if (value && typeof value === "object") Object.values(value).forEach(item => values(item, found));
  return found;
}

function exactSearch(kb, name) {
  const response = api("openapi/wiki/v1/search_knowledge", { query: name, knowledge_base_id: kb, cursor: "" });
  return values(response.data).some(value => value === name);
}

function repeatedName(kb, name, mediaType) {
  const response = api("openapi/wiki/v1/check_repeated_names", {
    params: [{ name, media_type: mediaType }],
    knowledge_base_id: kb,
  });
  const rows = response.data?.results || response.data?.check_results || response.data || [];
  return Array.isArray(rows) && rows.some(row => row?.is_repeated || row?.repeated);
}

function output(value, code = 0) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
  process.exit(code);
}

function main() {
  const args = parseArgs(process.argv);
  for (const required of [imaApiPath, preflightPath, cosUploadPath]) {
    if (!fs.existsSync(required)) throw new Error("IMA 官方上传组件缺失；请先安装 ima-skill");
  }
  const file = path.resolve(args.file);
  if (!fs.existsSync(file)) throw new Error("待上传图片不存在");
  if (path.basename(file) !== args.name) throw new Error("文件名必须与 IMA 知识标题完全一致");
  const preflight = JSON.parse(run("node", [preflightPath, "--file", file]));
  if (!preflight.pass) throw new Error(`图片预检失败：${preflight.reason || "未知原因"}`);
  if (exactSearch(args.kb, args.name)) {
    output({ status: "already_exists", fileName: args.name, verification: "exact_file_name" });
  }
  if (repeatedName(args.kb, args.name, preflight.media_type)) {
    output({ status: "needs_manual_duplicate_review", fileName: args.name, verification: "repeated_name" }, 3);
  }
  const created = api("openapi/wiki/v1/create_media", {
    file_name: args.name,
    file_size: preflight.file_size,
    content_type: preflight.content_type,
    knowledge_base_id: args.kb,
    file_ext: preflight.file_ext,
  });
  const media = created.data || {};
  const credential = media.cos_credential || {};
  if (!media.media_id || !credential.cos_key) throw new Error("IMA 未返回可用的文件上传凭证");
  run("node", [
    cosUploadPath,
    "--file", file,
    "--secret-id", credential.secret_id,
    "--secret-key", credential.secret_key,
    "--token", credential.token,
    "--bucket", credential.bucket_name,
    "--region", credential.region,
    "--cos-key", credential.cos_key,
    "--content-type", preflight.content_type,
    "--start-time", String(credential.start_time),
    "--expired-time", String(credential.expired_time),
    "--timeout", "300000",
  ]);
  api("openapi/wiki/v1/add_knowledge", {
    media_type: preflight.media_type,
    media_id: media.media_id,
    title: args.name,
    knowledge_base_id: args.kb,
    file_info: { cos_key: credential.cos_key, file_size: preflight.file_size, file_name: args.name },
  });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (exactSearch(args.kb, args.name)) output({ status: "completed", fileName: args.name, verification: "exact_file_name" });
    if (attempt < 2) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 2000);
  }
  output({ status: "verification_pending", fileName: args.name, verification: "not_indexed_yet" }, 4);
}

try { main(); } catch (error) {
  // Never echo request bodies, COS credentials, or API keys.
  output({ status: "failed", message: String(error?.message || error).slice(0, 500) }, 2);
}
