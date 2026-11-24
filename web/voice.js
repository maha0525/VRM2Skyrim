"use strict";
// Custom voice editor: 3-tier dialogue scenes, JSON import/export, AI prompt copy, per-line & ZIP audio upload.
const voiceState = {
  scenes: [],
  lines: {},          // scene_id -> [{ id: "01", text: "...", audio?: "..." }]
  linesDirty: false,  // true once user edits/imports lines so changing base voice won't overwrite
  uploaded: new Set(),// lowercased filenames uploaded to server
  tools: null,
  activeTier: "required",
  loadedGame: "",
  loadedVoice: "",
};

function initCustomVoice() {
  $("voice_mode").onchange = () => {
    const isCustom = $("voice_mode").value === "custom";
    $("custom-voice-panel").hidden = !isCustom;
    if (isCustom) ensureVoiceScenesLoaded();
  };
  $("voice").addEventListener("change", () => {
    if ($("voice_mode").value === "custom") ensureVoiceScenesLoaded(true);
  });
  document.querySelectorAll("[data-voice-tier]").forEach(btn => {
    btn.onclick = () => {
      voiceState.activeTier = btn.dataset.voiceTier;
      renderCustomVoice();
    };
  });
  $("voice-copy-prompt").onclick = copyVoicePrompt;
  $("voice-prompt-box").ontoggle = () => {
    if ($("voice-prompt-box").open) refreshVoicePromptPreview();
  };
  for (const id of ["npc_name", "sex", "voice-persona-style", "voice-persona-pronouns"]) {
    const el = $(id);
    if (el) el.addEventListener("input", () => {
      if ($("voice_mode").value === "custom" && $("voice-prompt-box").open) refreshVoicePromptPreview();
    });
  }
  $("voice-export-json").onclick = () => {
    download(($("mod_id").value || "follower") + "-voice.json", collectCustomVoiceLines());
  };
  $("voice-copy-tts-json").onclick = copyTtsBatchJson;
  $("voice-export-tts-json").onclick = () => {
    const items = collectTtsBatchItems($("voice-tts-unmatched-only")?.checked);
    if (!items.length) {
      $("voice-status").textContent = tr("出力対象のセリフがありません");
      return;
    }
    download(($("mod_id").value || "follower") + "-tts-batch.json", items);
    $("voice-status").textContent = items.length > 200
      ? tr("TTS用JSON（{0}件）を書き出しました（200件超はTTS側の上限に合わせて分割してください）", items.length)
      : tr("TTS用JSON（{0}件）を書き出しました", items.length);
  };
  $("voice-tts-unmatched-only").onchange = refreshTtsJsonPreview;
  $("voice-tts-box").ontoggle = () => {
    if ($("voice-tts-box").open) refreshTtsJsonPreview();
  };
  async function importVoiceJsonFile(file) {
    if (!file) return;
    try {
      applyVoiceJsonText(await file.text());
      $("voice-status").textContent = tr("セリフJSONを読み込みました");
    } catch (e) {
      error(e.message);
    } finally {
      $("voice-import-json").value = "";
    }
  }
  $("voice-import-json").onchange = () => importVoiceJsonFile($("voice-import-json").files[0]);
  bindFileDrop($("voice-import-json").closest("label"), importVoiceJsonFile);
  bindFileDrop($("voice-paste-json"), importVoiceJsonFile);
  $("voice-paste-apply").onclick = () => {
    const text = $("voice-paste-json").value.trim();
    if (!text) return;
    try {
      applyVoiceJsonText(text);
      $("voice-paste-json").value = "";
      $("voice-status").textContent = tr("貼り付けたJSONを反映しました");
    } catch (e) {
      error(e.message);
    }
  };
  async function uploadVoiceZipFile(file) {
    if (!file) return;
    $("voice-status").textContent = tr("音声ZIPを読み込んでいます…");
    try {
      const resp = await fetch("/api/voice-zip", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
        body: file,
      });
      const res = await resp.json();
      if (!resp.ok) throw new Error(res.error || tr("音声ZIPの読み込みに失敗しました"));
      voiceState.uploaded = new Set(res.files || []);
      renderCustomVoice();
      $("voice-status").textContent = tr("音声ZIPから {0} 件の音声を読み込みました", res.count);
    } catch (e) {
      error(e.message);
      $("voice-status").textContent = "";
    } finally {
      $("voice-zip-upload").value = "";
    }
  }
  $("voice-zip-upload").onchange = () => uploadVoiceZipFile($("voice-zip-upload").files[0]);
  bindFileDrop($("voice-zip-upload").closest("label"), uploadVoiceZipFile);
}

async function ensureVoiceScenesLoaded(force = false) {
  const game = $("game").value;
  const baseVoice = $("voice").value || "FemaleEvenToned";
  if (!force && voiceState.scenes.length && voiceState.loadedGame === game && voiceState.loadedVoice === baseVoice) {
    renderCustomVoice();
    return;
  }
  try {
    const res = await api(`/api/voice-scenes?game=${encodeURIComponent(game)}&voice=${encodeURIComponent(baseVoice)}`);
    voiceState.scenes = res.scenes || [];
    voiceState.tools = res.tools || null;
    voiceState.uploaded = new Set([...voiceState.uploaded, ...(res.uploaded_files || [])]);
    voiceState.loadedGame = game;
    voiceState.loadedVoice = baseVoice;
    if ((!voiceState.linesDirty || !Object.keys(voiceState.lines).length) && res.defaults) {
      voiceState.lines = structuredClone(res.defaults);
    }
    renderCustomVoice();
    refreshVoicePromptPreview();
  } catch (e) {
    error(e.message);
  }
}

function loadCustomVoiceSettings(settings) {
  const mode = settings.voice_mode || "official";
  $("voice_mode").value = mode;
  $("custom-voice-panel").hidden = mode !== "custom";
  voiceState.lines = structuredClone(settings.custom_voice_lines || {});
  voiceState.linesDirty = Object.keys(voiceState.lines).length > 0;
  if (mode === "custom") ensureVoiceScenesLoaded();
}

function collectCustomVoiceLines() {
  const out = {};
  for (const [sid, list] of Object.entries(voiceState.lines)) {
    const cleaned = (list || [])
      .filter(item => item && String(item.text || "").trim())
      .map(item => {
        const entry = { id: String(item.id), text: String(item.text).trim() };
        if (item.audio && String(item.audio).trim()) entry.audio = String(item.audio).trim();
        return entry;
      });
    if (cleaned.length) out[sid] = cleaned;
  }
  return out;
}

function collectTtsBatchItems(unmatchedOnly = false) {
  const items = [];
  const orderedIds = voiceState.scenes.length
    ? voiceState.scenes.map(s => s.id)
    : Object.keys(voiceState.lines);
  for (const sid of orderedIds) {
    for (const line of voiceState.lines[sid] || []) {
      const text = String(line?.text || "").trim();
      if (!text) continue;
      if (unmatchedOnly && matchedAudioFilename(sid, line)) continue;
      const rawAudio = line.audio ? String(line.audio).trim() : "";
      const stem = rawAudio
        ? rawAudio.replace(/^.*[\\/]/, "").replace(/\.(?:wav|ogg|mp3|flac|m4a)$/i, "")
        : `${sid}_${line.id}`;
      items.push({ filename: stem || `${sid}_${line.id}`, text });
    }
  }
  return items;
}

function refreshTtsJsonPreview() {
  const preview = $("voice-tts-preview");
  if (!preview) return;
  const items = collectTtsBatchItems($("voice-tts-unmatched-only")?.checked);
  preview.value = items.length ? JSON.stringify(items, null, 2) : "[]";
}

async function copyTtsBatchJson() {
  try {
    const items = collectTtsBatchItems($("voice-tts-unmatched-only")?.checked);
    refreshTtsJsonPreview();
    if (!items.length) {
      $("voice-status").textContent = tr("出力対象のセリフがありません");
      return;
    }
    const text = JSON.stringify(items, null, 2);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      $("voice-status").textContent = items.length > 200
        ? tr("TTS用JSON（{0}件）をクリップボードにコピーしました（200件超はTTS側の上限に合わせて分割してください）", items.length)
        : tr("TTS用JSON（{0}件）をクリップボードにコピーしました", items.length);
    } else {
      $("voice-tts-box").open = true;
      $("voice-status").textContent = tr("下の欄からTTS用JSONをコピーしてください");
    }
  } catch (e) {
    error(e.message);
  }
}

function nextLineId(list) {
  let maxNum = 0;
  for (const item of list || []) {
    const n = Number.parseInt(item.id, 10);
    if (Number.isFinite(n) && n > maxNum) maxNum = n;
  }
  return String(maxNum + 1).padStart(2, "0");
}

function applyVoiceJsonText(rawText) {
  // Strip optional markdown ```json fences if pasted from an LLM
  const stripped = rawText.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
  const parsed = JSON.parse(stripped);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(tr("JSONは場面IDをキーにしたオブジェクト形式で指定してください"));
  }
  const known = new Set(voiceState.scenes.map(s => s.id));
  for (const [sid, entries] of Object.entries(parsed)) {
    if (known.size && !known.has(sid)) continue;
    if (!Array.isArray(entries)) continue;
    const seen = new Set();
    let seq = 1;
    const normalized = [];
    for (const item of entries) {
      if (typeof item === "string") {
        const text = item.trim();
        if (!text) continue;
        while (seen.has(String(seq).padStart(2, "0"))) seq++;
        const id = String(seq).padStart(2, "0");
        seen.add(id);
        normalized.push({ id, text });
      } else if (item && typeof item === "object") {
        const text = String(item.text || "").trim();
        if (!text) continue;
        let id = String(item.id || "").trim();
        if (!id || seen.has(id)) {
          while (seen.has(String(seq).padStart(2, "0"))) seq++;
          id = String(seq).padStart(2, "0");
        }
        seen.add(id);
        const entry = { id, text };
        if (item.audio) entry.audio = String(item.audio).trim();
        normalized.push(entry);
      }
    }
    voiceState.lines[sid] = normalized;
  }
  voiceState.linesDirty = true;
  renderCustomVoice();
}

async function refreshVoicePromptPreview() {
  if ($("voice_mode").value !== "custom") return null;
  const res = await api("/api/voice-prompt", {
    game: $("game").value,
    voice: $("voice").value || "FemaleEvenToned",
    npc_name: $("npc_name").value || "",
    sex: $("sex").value || "female",
    style: $("voice-persona-style")?.value || "",
    pronouns: $("voice-persona-pronouns")?.value || "",
    lang: i18n.language === "en" ? "en" : "ja",
  });
  $("voice-prompt-preview").value = res.prompt;
  return res.prompt;
}

async function copyVoicePrompt() {
  try {
    const prompt = await refreshVoicePromptPreview();
    $("voice-prompt-box").open = true;
    if (prompt && navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(prompt);
      $("voice-status").textContent = tr("AI用プロンプトをクリップボードにコピーしました");
    } else {
      $("voice-status").textContent = tr("下の欄からAI用プロンプトをコピーしてください");
    }
  } catch (e) {
    error(e.message);
  }
}

function matchedAudioFilename(sceneId, line) {
  const candidates = [];
  if (line.audio) candidates.push(line.audio.toLowerCase());
  const base = `${sceneId}_${line.id}`.toLowerCase();
  for (const ext of [".wav", ".ogg", ".mp3", ".flac", ".m4a"]) candidates.push(base + ext);
  return candidates.find(c => voiceState.uploaded.has(c)) || null;
}

function renderCustomVoice() {
  if ($("voice_mode").value !== "custom") return;
  const tools = voiceState.tools;
  if (tools) {
    const parts = [];
    parts.push(tools.can_fuz ? "xwmaencode (.fuz) ✓" : tr("xwmaencode なし（.wav出力）"));
    parts.push(tools.can_lip ? "FaceFX (.lip) ✓" : tr("FaceFX なし（口パクなし）"));
    parts.push(tools.ffmpeg ? "ffmpeg ✓" : tr("ffmpeg なし（44.1kHz 16bit mono .wavのみ）"));
    $("voice-tools-status").textContent = parts.join(" · ");
  }

  let totalLines = 0, matchedCount = 0;
  for (const scene of voiceState.scenes) {
    for (const line of voiceState.lines[scene.id] || []) {
      if (!String(line.text || "").trim()) continue;
      totalLines++;
      if (matchedAudioFilename(scene.id, line)) matchedCount++;
    }
  }
  $("voice-summary-bar").textContent = tr("登録セリフ: {0}本 · 音声割当済み: {1}本（未割当は字幕表示用の無音を自動生成）", totalLines, matchedCount);

  document.querySelectorAll("[data-voice-tier]").forEach(btn => {
    const tier = btn.dataset.voiceTier;
    const tierScenes = voiceState.scenes.filter(s => s.tier === tier);
    const filled = tierScenes.filter(s => (voiceState.lines[s.id] || []).some(l => String(l.text || "").trim())).length;
    btn.classList.toggle("active", tier === voiceState.activeTier);
    const baseLabel = tier === "required" ? tr("必須") : tier === "recommended" ? tr("推奨") : tr("任意");
    btn.textContent = `${baseLabel} (${filled}/${tierScenes.length})`;
  });

  const container = $("voice-scenes-list");
  container.replaceChildren();
  const lang = i18n.language === "en" ? "en" : "ja";

  for (const scene of voiceState.scenes.filter(s => s.tier === voiceState.activeTier)) {
    const card = document.createElement("div");
    card.className = "voice-scene-card";
    const head = document.createElement("div");
    head.className = "voice-scene-head";
    const title = document.createElement("strong");
    title.textContent = (lang === "en" ? scene.label_en : scene.label_ja) + ` (${scene.id})`;
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "secondary small";
    addBtn.textContent = tr("＋ セリフ追加");
    addBtn.onclick = () => {
      const list = voiceState.lines[scene.id] || (voiceState.lines[scene.id] = []);
      list.push({ id: nextLineId(list), text: "" });
      voiceState.linesDirty = true;
      renderCustomVoice();
    };
    head.append(title, addBtn);
    card.append(head);

    const ctx = document.createElement("p");
    ctx.className = "hint";
    ctx.textContent = lang === "en" ? scene.context_en : scene.context_ja;
    card.append(ctx);

    const sampleList = (scene.samples?.[lang]?.length ? scene.samples[lang] : scene.samples?.ja) || [];
    if (sampleList.length) {
      const sampleEl = document.createElement("p");
      sampleEl.className = "voice-sample";
      sampleEl.textContent = tr("公式見本: ") + sampleList.slice(0, 3).join(lang === "en" ? " / " : " ／ ");
      card.append(sampleEl);
    }

    const list = voiceState.lines[scene.id] || [];
    for (let idx = 0; idx < list.length; idx++) {
      const line = list[idx];
      const row = document.createElement("div");
      row.className = "voice-line-row";
      const idBadge = document.createElement("code");
      idBadge.className = "voice-line-id";
      idBadge.textContent = `${scene.id}_${line.id}`;

      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 250;
      input.value = line.text || "";
      input.placeholder = tr("セリフを入力");
      input.oninput = () => {
        line.text = input.value;
        voiceState.linesDirty = true;
        if ($("voice-tts-box")?.open) refreshTtsJsonPreview();
      };

      const matched = matchedAudioFilename(scene.id, line);
      const audioLabel = document.createElement("label");
      audioLabel.className = "voice-audio-btn secondary small";
      audioLabel.textContent = matched ? `♪ ${matched}` : tr("音声を選択");
      const fileIn = document.createElement("input");
      fileIn.type = "file";
      fileIn.accept = ".wav,.ogg,.mp3,.flac,.m4a";
      fileIn.hidden = true;
      const uploadSingleAudio = async (f) => {
        if (!f) return;
        try {
          const resp = await fetch("/api/voice-audio", {
            method: "POST",
            headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(f.name) },
            body: f,
          });
          const res = await resp.json();
          if (!resp.ok) throw new Error(res.error || tr("音声の読み込みに失敗しました"));
          line.audio = res.filename;
          voiceState.uploaded = new Set(res.files || []);
          renderCustomVoice();
        } catch (e) {
          error(e.message);
        } finally {
          fileIn.value = "";
        }
      };
      fileIn.onchange = () => uploadSingleAudio(fileIn.files[0]);
      audioLabel.append(fileIn);
      bindFileDrop(audioLabel, uploadSingleAudio);
      bindFileDrop(row, uploadSingleAudio);

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "secondary small";
      delBtn.textContent = "×";
      delBtn.title = tr("削除");
      delBtn.onclick = () => {
        list.splice(idx, 1);
        voiceState.linesDirty = true;
        renderCustomVoice();
      };

      row.append(idBadge, input, audioLabel, delBtn);
      card.append(row);
    }
    container.append(card);
  }
  refreshTtsJsonPreview();
}
