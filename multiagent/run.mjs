#!/usr/bin/env node
/**
 * run.mjs — «несколько агентов» для pi (https://github.com/earendil/pi-coding-agent).
 *
 * Запускает несколько параллельных pi-агентов (через SDK, createAgentSession),
 * каждый со своим контекстом, моделью и инструментами. Работает из любого каталога,
 * файлы правятся агентом в его cwd. Результаты пишутся в out/<id>.md.
 *
 * Резюме по использованию:
 *   - подготовить подзадачи (манифест JSON или папку *.task.md);
 *   - запустить:  node multiagent/run.mjs --dir multiagent/tasks --cwd "C:/path/to/project"
 *   - флаги: --parallel N (макс. одновременных агентов, по умолчанию 4), --dry-run (без вызова модели),
 *            --prompt "строка" --id имя (разовая задача), --out папка для результатов (по умолчанию multiagent/out).
 *   - каждый результат — out/<id>.md; агент также может менять файлы проекта сам.
 *
 * ВАЖНО: это настоящие LLM-вызовы той же модели, что и у вас в pi, с тем же аккаунтом/квотой.
 * Держите промпты узкими и по одной задаче; не запускайте больше ~4–6 параллельно, если нет
 * лишней квоты. Для проверки раскладки используйте --dry-run.
 */
import { readFile, readdir, mkdir, writeFile } from "node:fs/promises";
import { join, resolve, basename } from "node:path";
import { homedir } from "node:os";
import { pathToFileURL } from "node:url";
import { existsSync, readdirSync } from "node:fs";

/** Найти установленный SDK @earendil-works/pi-coding-agent (стабильный путь там же, где pi). */
function findSdkRoot() {
  const cands = [];
  if (process.env.PI_SDK && existsSync(join(process.env.PI_SDK, "dist", "index.js"))) cands.push(process.env.PI_SDK);
  const roots = [];
  if (process.env.PI_HOME) roots.push(process.env.PI_HOME);
  roots.push(join(homedir(), ".pi", "agent", "install"));
  for (const root of roots) {
    const releases = join(root, "releases");
    if (!existsSync(releases)) continue;
    for (const d of readdirSync(releases)) {
      const p = join(releases, d, "node_modules", "@earendil-works", "pi-coding-agent");
      if (existsSync(join(p, "dist", "index.js"))) cands.push(p);
    }
  }
  if (!cands.length) {
    console.error("[multiagent] SDK pi не найден. Поставьте в проект: npm i @earendil-works/pi-coding-agent, или задайте PI_SDK.");
    process.exit(2);
  }
  cands.sort((a, b) => (b > a ? 1 : -1));
  return cands[0];
}

const sdkRoot = findSdkRoot();
const { createAgentSession, ModelRuntime } = await import(pathToFileURL(join(sdkRoot, "dist", "index.js")).href);

const args = {};
for (let i = 2; i < process.argv.length; i++) {
  const a = process.argv[i];
  if (!a.startsWith("--")) continue;
  const key = a.slice(2);
  if (key === "dry-run") { args[key] = "true"; continue; }   // булев флаг — не съедает следующий аргумент
  args[key] = process.argv[++i];
}
const parallel = Math.max(1, parseInt(args.parallel || "4", 10) || 4);
const dry = args["dry-run"] === "true" || args["dry-run"] === "";
const cwd = resolve(args.cwd || process.cwd());
const outDir = resolve(args.out || join(".", "multiagent", "out"));
const self = new URL(import.meta.url).pathname;

// ---- собрать список подзадач: манифест JSON | папка *.task.md | разовая задача ----
async function gatherTasks() {
  const tasks = [];
  if (args.prompt && args.id) {
    tasks.push({ id: args.id, prompt: args.prompt });
  }
  if (args.dir) {
    const dir = resolve(args.dir);
    for (const f of (await readdir(dir)).filter((f) => f.endsWith(".task.md")).sort()) {
      tasks.push({ id: basename(f, ".task.md"), prompt: await readFile(join(dir, f), "utf-8") });
    }
  }
  if (args.manifest) {
    const m = JSON.parse(await readFile(resolve(args.manifest), "utf-8"));
    const t = m.tasks || (Array.isArray(m) ? m : []);
    for (const x of t) tasks.push({ id: x.id, prompt: x.prompt || x.task || x.brief });
  }
  return tasks.filter((t) => t.prompt && t.id);
}

function brief(t) {
  return `Вы — pi-агент, работающий в каталоге: ${cwd}\n` +
         `Пришлите подробное текстовое решение/анализ/код по задаче ниже.\n` +
         `Если нужно — смотрите и правите файлы в этом каталоге инструментами.\n` +
         `Обязательно завершите ответ строкой вида: RESULT_OK (или RESULT_FAIL: причина).\n` +
         `--- ЗАДАЧА [${t.id}] ---\n${t.prompt}`;
}

// ---- модель: PI_PROVIDER/PI_MODEL (как в основном сеансе) -> первая доступная -> дефолт SDK ----
const modelRuntime = await ModelRuntime.create();
let model = null;
if (process.env.PI_PROVIDER && process.env.PI_MODEL) {
  model = modelRuntime.getModel(process.env.PI_PROVIDER, process.env.PI_MODEL) || null;
  if (model) console.log(`[multiagent] модель из окружения: ${model.provider}/${model.id}`);
  else console.warn(`[multiagent] ${process.env.PI_PROVIDER}/${process.env.PI_MODEL} не найдена — беру дефолт`);
}
if (!model) {
  const avail = await modelRuntime.getAvailable();
  if (avail.length) { model = avail[0]; console.log(`[multiagent] модель: ${model.provider}/${model.id} (первая доступная)`); }
  else console.warn("[multiagent] доступных моделей нет — создаётся сессия с дефолтом SDK (может быть без ключа)");
}

async function run(t) {
  const { session } = await createAgentSession({ cwd, model, modelRuntime });
  try {
    if (dry) return { id: t.id, ok: true, preview: "DRY-RUN (модель не вызывалась)" };
    await session.prompt(brief(t));
    const text = session.getLastAssistantText() || "";
    const ok = /RESULT_OK/.test(text);
    await writeFile(join(outDir, `${t.id}.md`), text, "utf-8");
    return { id: t.id, ok, preview: text.slice(0, 220).replace(/\s+/g, " ") };
  } catch (e) {
    return { id: t.id, ok: false, error: String(e && e.message || e), preview: "" };
  } finally {
    session.dispose();
  }
}

await mkdir(outDir, { recursive: true });
const tasks = await gatherTasks();
if (!tasks.length) {
  console.error("Нет задач. Используйте --prompt+--id, --dir (папка *.task.md) или --manifest (json).");
  process.exit(2);
}
console.log(`[multiagent] задач=${tasks.length}, параллельно=${parallel}, cwd=${cwd}, dry=${dry}, out=${outDir}`);
// пол-пула
const results = [];
let next = 0;
async function worker() {
  while (next < tasks.length) {
    const t = tasks[next++];
    const r = await run(t);
    results.push(r);
    console.log(`  [${r.id}] ${r.ok ? "OK" : "FAIL"}${r.error ? " · " + r.error : ""}${r.preview ? " | " + r.preview : ""}`);
  }
}
await Promise.all(Array.from({ length: Math.min(parallel, tasks.length) }, worker));
const bad = results.filter((r) => !r.ok);
console.log(bad.length
  ? `[multiagent] Готово: ${results.length - bad.length}/${results.length} успешно. Результаты: ${outDir}`
  : `[multiagent] Все ${results.length} задач успешны. Результаты: ${outDir}`);
process.exit(bad.length ? 1 : 0);
