const fs = require("fs");
const path = require("path");

const repoRoot = __dirname;
const configPath = path.join(repoRoot, "config.json");
const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const outputDir = path.join(repoRoot, "outputs", "danmaku-tts");
const port = process.env.DANMAKU_TTS_PORT || "7910";
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
        path.join(repoRoot, "tools", "rvc_danmaku_server.py"),
        "--config",
        configPath,
        "--port",
        port,
      ],
      cwd: repoRoot,
      interpreter: "none",
      autorestart: true,
      restart_delay: 5000,
      exp_backoff_restart_delay: 1000,
      max_restarts: 10,
      min_uptime: "30s",
      kill_timeout: 10000,
      max_memory_restart: "12G",
      time: true,
      merge_logs: true,
      out_file: path.join(outputDir, "pm2-out.log"),
      error_file: path.join(outputDir, "pm2-error.log"),
      env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
        DANMAKU_TTS_PORT: port,
      },
    },
  ],
};
