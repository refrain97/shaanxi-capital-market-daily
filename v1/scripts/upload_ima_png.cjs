#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const skillRoot =
  process.env.IMA_SKILL_ROOT ||
  path.join(os.homedir(), ".workbuddy/skills-marketplace/skills/ima-skills");
const imaApiPath = path.join(skillRoot, "ima_api.cjs");
const preflightPath = path.join(skillRoot, "knowledge-base/scripts/preflight-check.cjs");
const cosUploadPath = path.join(skillRoot, "knowledge-base/scripts/cos-upload.cjs");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length;) {
    const key = argv[i];
    if (key === "--check-auth") {
      args["check-auth"] = "1";
      i += 1;
      continue;
    }
    const value = argv[i + 1];
    if (!key || !key.startsWith("--") || value === undefined) {
      throw new Error(`Bad argument near ${key || "(end)"}`);
    }
    args[key.slice(2)] = value;
    i += 2;
  }
  if (args["check-auth"]) return args;
  for (const key of ["file", "name", "record", "kb"]) {
    if (!args[key]) throw new Error(`Missing --${key}`);
  }
  return args;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: "utf8", ...options });
  if (result.status !== 0) {
    throw new Error(`${command} failed: ${result.stderr || result.stdout}`);
  }
  return result.stdout.trim();
}

function api(apiPath, body) {
  const raw = run("node", [imaApiPath, apiPath, JSON.stringify(body)]);
  const parsed = JSON.parse(raw || "{}");
  if (parsed.code !== 0) {
    if (parsed.code === 200002 || /auth failed/i.test(String(parsed.msg || ""))) {
      throw new Error(
        `IMA API ${apiPath} auth failed: ${raw}\n` +
          "Please refresh the IMA OpenAPI Client ID / API Key at https://ima.qq.com/agent-interface " +
          "and save them to ~/.config/ima/client_id and ~/.config/ima/api_key."
      );
    }
    throw new Error(`IMA API ${apiPath} failed: ${raw}`);
  }
  return parsed;
}

function uniqueName(fileName, repeatedResp) {
  const list = repeatedResp.data?.results || repeatedResp.data?.check_results || repeatedResp.data || [];
  const repeated = Array.isArray(list) && list.some((item) => item.is_repeated || item.repeated);
  if (!repeated) return { fileName, usedDuplicateSuffix: false };
  const ext = path.extname(fileName);
  const stem = fileName.slice(0, fileName.length - ext.length);
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const suffix = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return { fileName: `${stem}_${suffix}${ext}`, usedDuplicateSuffix: true };
}

function searchHit(kbId, query) {
  const resp = api("openapi/wiki/v1/search_knowledge", {
    query,
    knowledge_base_id: kbId,
    cursor: "",
  });
  const data = resp.data || {};
  const items = data.info_list || data.knowledge_list || data.list || [];
  return JSON.stringify(items).includes(query.replace(/_\\d{14}(?=\\.png$)/, ""));
}

function main() {
  const args = parseArgs(process.argv);
  if (args["check-auth"]) {
    if (!args.kb) throw new Error("Missing --kb");
    api("openapi/wiki/v1/get_knowledge_base", { ids: [args.kb] });
    process.stdout.write("IMA auth check: ok");
    return;
  }
  const filePath = path.resolve(args.file);
  const kbId = args.kb;
  const recordPath = path.resolve(args.record);

  const preflight = JSON.parse(run("node", [preflightPath, "--file", filePath]));
  if (!preflight.pass) {
    throw new Error(`Preflight failed: ${preflight.reason || JSON.stringify(preflight)}`);
  }

  const repeated = api("openapi/wiki/v1/check_repeated_names", {
    params: [{ name: args.name, media_type: preflight.media_type }],
    knowledge_base_id: kbId,
  });
  const finalName = uniqueName(args.name, repeated);

  const createMedia = api("openapi/wiki/v1/create_media", {
    file_name: finalName.fileName,
    file_size: preflight.file_size,
    content_type: preflight.content_type,
    knowledge_base_id: kbId,
    file_ext: preflight.file_ext,
  });
  const media = createMedia.data || {};
  const cred = media.cos_credential || {};
  const mediaId = media.media_id;
  if (!mediaId || !cred.cos_key) {
    throw new Error(`Unexpected create_media response: ${JSON.stringify(createMedia)}`);
  }

  run("node", [
    cosUploadPath,
    "--file",
    filePath,
    "--secret-id",
    cred.secret_id,
    "--secret-key",
    cred.secret_key,
    "--token",
    cred.token,
    "--bucket",
    cred.bucket_name,
    "--region",
    cred.region,
    "--cos-key",
    cred.cos_key,
    "--content-type",
    preflight.content_type,
    "--start-time",
    String(cred.start_time),
    "--expired-time",
    String(cred.expired_time),
    "--timeout",
    "300000",
  ]);

  const addKnowledge = api("openapi/wiki/v1/add_knowledge", {
    media_type: preflight.media_type,
    media_id: mediaId,
    title: finalName.fileName,
    knowledge_base_id: kbId,
    file_info: {
      cos_key: cred.cos_key,
      file_size: preflight.file_size,
      file_name: finalName.fileName,
    },
  });

  const exactHit = searchHit(kbId, finalName.fileName);
  const keyword = args.keyword || finalName.fileName.replace(/\\.png$/, "").replace(/^\\d{4}年\\d+月\\d+日/, "");
  const keywordHit = searchHit(kbId, keyword);
  const verified = exactHit || keywordHit;

  const record = {
    uploadStatus: verified ? "success" : "verification_failed",
    knowledgeBaseName: args.kbName || "公告检索",
    knowledgeBaseId: kbId,
    recommendedFileName: args.name,
    uploadedFileName: finalName.fileName,
    mediaId,
    localFile: args.local || args.file,
    imageFile: args.local || args.file,
    addKnowledgeResponse: addKnowledge,
    searchVerified: {
      exactFileName: exactHit,
      dateKeyword: keywordHit,
    },
    verificationMode: exactHit ? "exactFileName" : (keywordHit ? "dateKeyword" : "none"),
    usedDuplicateSuffix: finalName.usedDuplicateSuffix,
    verificationQuery: finalName.fileName,
    uploadedAt: new Date().toISOString(),
  };
  fs.mkdirSync(path.dirname(recordPath), { recursive: true });
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2), "utf8");
  process.stdout.write(JSON.stringify(record, null, 2));
}

try {
  main();
} catch (error) {
  console.error(error.message || error);
  process.exit(1);
}
