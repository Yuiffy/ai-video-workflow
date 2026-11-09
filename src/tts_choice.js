const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="studio-token"]').content;
let candidates = [];
let selected = "";
let activeFilter = "all";

function message(text, error = false) {
  $("message").textContent = text;
  $("message").className = error ? "error" : "";
}

function danmakuStatus(data) {
  const labels = {
    cold: "冷启动 · 模型未加载",
    loading: "正在加载模型",
    ready: "热运行 · 可直接朗读",
    offline: "后台服务未启动",
    error: "模型加载失败",
  };
  $("danmaku-status").textContent = labels[data.status] || data.status || "未知状态";
  $("danmaku-status").dataset.state = data.status || "";
}

async function refreshDanmaku() {
  try {
    danmakuStatus(await api("/api/danmaku"));
  } catch (error) {
    danmakuStatus({status: "offline"});
  }
}

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Studio-Token": token},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "操作失败");
  return data;
}

function category(candidate) {
  if (candidate.id === "minimax") return "cloud";
  if (candidate.id === "rvc-v2-p5" || candidate.id === "rvc-v3-e10") return "live";
  return "offline";
}

function visible(candidate) {
  return activeFilter === "all" || category(candidate) === activeFilter;
}

function makeCard(candidate) {
  const article = document.createElement("article");
  article.className = `card${candidate.id === selected ? " selected" : ""}`;
  article.dataset.id = candidate.id;
  const audio = candidate.audio_url
    ? `<audio controls preload="none" src="${candidate.audio_url}"></audio>`
    : `<div class="no-audio">当前没有可试听样例</div>`;
  article.innerHTML = `
    <div class="card-head">
      <div><span class="kind">${candidate.kind}</span><h2>${candidate.name}</h2></div>
      <span class="tone">${candidate.tone}</span>
    </div>
    <p>${candidate.summary}</p>
    ${audio}
    <dl>
      <div><dt>适合</dt><dd>${candidate.fit}</dd></div>
      <div><dt>速度</dt><dd>${candidate.latency}</dd></div>
      <div><dt>占用</dt><dd>${candidate.memory}</dd></div>
      <div><dt>依据</dt><dd>${candidate.quality}</dd></div>
    </dl>
    <button class="choose">${candidate.id === selected ? "已选择" : "选这个"}</button>
  `;
  article.querySelector(".choose").addEventListener("click", () => {
    selected = candidate.id;
    render();
    message(`已选中：${candidate.name}，保存后生效。`);
  });
  return article;
}

function render() {
  const cards = candidates.filter(visible).map(makeCard);
  $("candidate-grid").replaceChildren(...cards);
  const current = candidates.find((item) => item.id === selected);
  $("selected-name").textContent = current ? current.name : "尚未选择";
}

function apply(data) {
  candidates = data.candidates || [];
  selected = data.selected || "";
  $("note").value = data.note || "";
  render();
}

document.querySelectorAll(".filter").forEach((button) => {
  button.addEventListener("click", () => {
    activeFilter = button.dataset.filter;
    document.querySelectorAll(".filter").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    render();
  });
});

$("save").addEventListener("click", async () => {
  if (!selected) return message("先选择一个声音方案。", true);
  $("save").disabled = true;
  try {
    apply(await api("/api/tts-choice", {selected, note: $("note").value}));
    message("选择已保存在本机。");
  } catch (error) {
    message(error.message, true);
  } finally {
    $("save").disabled = false;
  }
});

$("warm").addEventListener("click", async () => {
  $("warm").disabled = true;
  try {
    danmakuStatus(await api("/api/danmaku", {action: "warm"}));
    message("模型开始加载，通常需要 30–50 秒。");
  } catch (error) {
    message(error.message, true);
  } finally {
    $("warm").disabled = false;
  }
});

$("unload").addEventListener("click", async () => {
  $("unload").disabled = true;
  try {
    danmakuStatus(await api("/api/danmaku", {action: "unload"}));
    message("模型进程已退出，内存和显存已释放。");
  } catch (error) {
    message(error.message, true);
  } finally {
    $("unload").disabled = false;
  }
});

api("/api/tts-choice").then(apply).catch((error) => message(error.message, true));
refreshDanmaku();
setInterval(refreshDanmaku, 5000);
