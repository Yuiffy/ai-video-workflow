const fs = require("fs");
const path = require("path");

const repoRoot = __dirname;
const configPath = path.join(repoRoot, "config.json");
const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const outputDir = path.join(repoRoot, "outputs", "danmaku-tts");
const port = process.env.DANMAKU_TTS_PORT || "7910";
const rvcModel =
  process.env.DANMAKU_RVC_MODEL ||
  path.join(
    repoRoot,
    "outputs",
    "sui-voice-20260928",
    "rvc",
    "sui_v3_48k.pth",
  );
const rvcIndex =
  process.env.DANMAKU_RVC_INDEX ||
  path.join(
    repoRoot,
    "outputs",
    "sui-voice-20260928",
    "rvc",
    "sui_v3_48k.index",
  );
const pythonw = path.join(path.dirname(config.rvc.runtime_python), "pythonw.exe");
const runtime =
  process.platform === "win32" && fs.existsSync(pythonw)
    ? pythonw
    : config.rvc.runtime_python;

module.exports = {
  apps: [
    {
      name: "danmaku-tts",
      script: runtime,
      args: [
        path.join(repoRoot, "tools", "danmaku_tts_supervisor.py"),
        "--config",
        configPath,
        "--port",
        port,
      ],
      cwd: repoRoot,
      interpreter: "none",
      windowsHide: true,
      autorestart: true,
      restart_delay: 5000,
      exp_backoff_restart_delay: 1000,
      max_restarts: 10,
      min_uptime: "30s",
      kill_timeout: 10000,
      max_memory_restart: "1G",
      time: true,
      merge_logs: true,
      out_file: path.join(outputDir, "pm2-out.log"),
      error_file: path.join(outputDir, "pm2-error.log"),
      env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
        DANMAKU_TTS_SILENT: "1",
        DANMAKU_TTS_PORT: port,
        DANMAKU_RVC_MODEL: rvcModel,
        DANMAKU_RVC_INDEX: rvcIndex,
        DANMAKU_RVC_PITCH: process.env.DANMAKU_RVC_PITCH || "1",
        DANMAKU_RVC_INDEX_SAMPLE_SIZE:
          process.env.DANMAKU_RVC_INDEX_SAMPLE_SIZE || "65536",
        DANMAKU_TTS_IDLE_UNLOAD_SECONDS:
          process.env.DANMAKU_TTS_IDLE_UNLOAD_SECONDS || "300",
        DANMAKU_TTS_AUTO_WARM: process.env.DANMAKU_TTS_AUTO_WARM || "1",
        DANMAKU_TTS_HOST_PROCESS:
          process.env.DANMAKU_TTS_HOST_PROCESS || "Bililive_dm.exe",
      },
    },
  ],
};
