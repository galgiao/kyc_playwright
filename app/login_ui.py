LOGIN_UI_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>企查查登录</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1d2433;
      --muted: #657083;
      --line: #d9dee7;
      --accent: #176b5f;
      --accent-strong: #0f4f46;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }
    main { padding: 16px; }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    button, input {
      height: 36px;
      border-radius: 6px;
      border: 1px solid var(--line);
      font: inherit;
    }
    input {
      width: min(360px, 100%);
      padding: 0 10px;
      background: white;
    }
    button {
      padding: 0 12px;
      background: white;
      color: var(--text);
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    button.primary:hover { background: var(--accent-strong); }
    .meta {
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .viewport {
      margin-top: 14px;
      overflow: auto;
      border: 1px solid var(--line);
      background: #eef1f5;
      border-radius: 6px;
      min-height: 520px;
      position: relative;
    }
    .placeholder {
      display: grid;
      place-items: center;
      min-height: 520px;
      color: var(--muted);
      font-size: 14px;
    }
    #screen {
      display: none;
      width: min(100%, 1440px);
      height: auto;
      cursor: crosshair;
      user-select: none;
    }
    #toast {
      min-width: 220px;
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }
  </style>
</head>
<body>
  <header>
    <h1>企查查登录</h1>
    <div id="toast">等待启动</div>
  </header>
  <main>
    <div class="toolbar">
      <button class="primary" id="start">启动</button>
      <button id="refresh">刷新截图</button>
      <input id="text" autocomplete="off" placeholder="输入内容">
      <button id="type">输入</button>
      <button data-key="Tab">Tab</button>
      <button data-key="Enter">Enter</button>
      <button data-key="Backspace">Backspace</button>
      <button class="primary" id="save">保存登录态</button>
    </div>
    <div class="meta" id="meta"></div>
    <div class="viewport">
      <div class="placeholder" id="placeholder">正在启动服务器浏览器...</div>
      <img id="screen" alt="">
    </div>
  </main>
  <script>
    const screen = document.getElementById("screen");
    const placeholder = document.getElementById("placeholder");
    const toast = document.getElementById("toast");
    const meta = document.getElementById("meta");
    const text = document.getElementById("text");
    let statusTimer = null;

    function note(message) {
      toast.textContent = message;
    }

    async function postJson(url, body = {}) {
      const response = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || response.statusText);
      return payload;
    }

    async function refreshStatus() {
      const response = await fetch("/auth/session/status");
      const payload = await response.json();
      meta.textContent = payload.active ? `${payload.title || ""} ${payload.url || ""}` : "未启动";
      if (!payload.active && statusTimer) {
        clearInterval(statusTimer);
        statusTimer = null;
      }
      return payload;
    }

    async function refreshScreen() {
      placeholder.style.display = "grid";
      placeholder.textContent = "正在刷新截图...";
      const nextSrc = `/auth/session/screenshot?t=${Date.now()}`;
      await new Promise((resolve, reject) => {
        screen.onload = resolve;
        screen.onerror = () => reject(new Error("截图加载失败，请检查服务端 Playwright 是否启动"));
        screen.src = nextSrc;
      });
      screen.style.display = "block";
      placeholder.style.display = "none";
      await refreshStatus();
    }

    async function startSession() {
      try {
        note("正在启动");
        placeholder.textContent = "正在启动服务器浏览器...";
        await postJson("/auth/session/start");
        note("已启动");
        await refreshScreen();
      } catch (error) {
        note(error.message);
        placeholder.textContent = error.message;
      }
    }

    document.getElementById("start").onclick = startSession;

    document.getElementById("refresh").onclick = refreshScreen;

    document.getElementById("type").onclick = async () => {
      try {
        await postJson("/auth/session/type", {text: text.value});
        text.value = "";
        await refreshScreen();
      } catch (error) {
        note(error.message);
      }
    };

    document.querySelectorAll("button[data-key]").forEach((button) => {
      button.onclick = async () => {
        try {
          await postJson("/auth/session/press", {key: button.dataset.key});
          await refreshScreen();
        } catch (error) {
          note(error.message);
        }
      };
    });

    document.getElementById("save").onclick = async () => {
      try {
        const payload = await postJson("/auth/session/save");
        note(`已保存 ${payload.storage_state_path}`);
        if (statusTimer) {
          clearInterval(statusTimer);
          statusTimer = null;
        }
        screen.removeAttribute("src");
        screen.style.display = "none";
        placeholder.style.display = "grid";
        placeholder.textContent = "登录态已保存，可以关闭此页面。";
        meta.textContent = "登录会话已结束";
      } catch (error) {
        note(error.message);
      }
    };

    screen.onclick = async (event) => {
      if (!screen.naturalWidth || !screen.naturalHeight) return;
      const rect = screen.getBoundingClientRect();
      const x = (event.clientX - rect.left) * (screen.naturalWidth / rect.width);
      const y = (event.clientY - rect.top) * (screen.naturalHeight / rect.height);
      try {
        await postJson("/auth/session/click", {x, y});
        await refreshScreen();
      } catch (error) {
        note(error.message);
      }
    };

    statusTimer = setInterval(() => {
      if (screen.src) refreshStatus();
    }, 3000);

    window.addEventListener("load", startSession);
  </script>
</body>
</html>
"""
