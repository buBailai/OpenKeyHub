'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
let SETUP = false;

async function api(method, path, body) {
  const opt = { method, headers: {}, credentials: 'same-origin' };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch('/api/admin' + path, opt);
  let data = null; try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((data && data.detail) || ('错误 ' + r.status));
  return data;
}
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add('hidden'), 2200);
}
function modal(html) {
  $('#modal').innerHTML = html; $('#modalBg').classList.remove('hidden');
}
function closeModal() { $('#modalBg').classList.add('hidden'); }
$('#modalBg').addEventListener('click', e => { if (e.target.id === 'modalBg') closeModal(); });

/* ---------- 登录 / 首次设置 ---------- */
async function boot() {
  let st;
  try { st = await api('GET', '/state'); } catch (e) { st = { setup_required: true, logged_in: false }; }
  if (st.logged_in) return enterApp();
  SETUP = st.setup_required;
  $('#gate').classList.remove('hidden');
  $('#gateSub').textContent = SETUP ? '首次启动，请创建管理员账号' : '学校统一配 Key，分发给老师';
  $('#gBtn').textContent = SETUP ? '创建管理员' : '登录';
  $('#gPass').autocomplete = SETUP ? 'new-password' : 'current-password';
}
$('#gateForm').addEventListener('submit', async e => {
  e.preventDefault();
  const username = $('#gUser').value.trim(), password = $('#gPass').value;
  const h = $('#gHint'); h.textContent = ''; h.className = 'hint';
  if (!username || !password) { h.textContent = '请填写账号和密码'; h.classList.add('err'); return; }
  try {
    await api('POST', SETUP ? '/setup' : '/login', { username, password });
    $('#gate').classList.add('hidden'); enterApp();
  } catch (err) { h.textContent = err.message; h.classList.add('err'); }
});

function enterApp() {
  $('#app').classList.remove('hidden');
  fetch('/health').then(r => r.json()).then(d => { $('#ver').textContent = 'v' + d.version; }).catch(() => {});
  const tabs = ['overview', 'providers', 'models', 'accounts', 'logs', 'update'];
  const start = location.hash.slice(1);
  switchTab(tabs.includes(start) ? start : 'overview');
}
window.addEventListener('hashchange', () => {
  const t = location.hash.slice(1);
  if (['overview', 'providers', 'models', 'accounts', 'logs', 'update'].includes(t)) switchTab(t);
});
$('#logoutBtn').addEventListener('click', async () => { await api('POST', '/logout'); location.reload(); });
$('#nav').addEventListener('click', e => { if (e.target.dataset.tab) switchTab(e.target.dataset.tab); });

function switchTab(tab) {
  if (location.hash.slice(1) !== tab) history.replaceState(null, '', '#' + tab);
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  $$('.view').forEach(v => v.classList.toggle('hidden', v.dataset.view !== tab));
  ({ overview: loadOverview, providers: loadProviders, models: loadModels,
     accounts: loadAccounts, logs: loadLogs, update: loadUpdate }[tab] || (() => {}))();
}

/* ---------- 概览 ---------- */
async function loadOverview() {
  const s = await api('GET', '/stats');
  const fail = s.total_calls - s.ok_calls;
  $('#statCards').innerHTML = [
    ['总调用次数', s.total_calls],
    ['成功', s.ok_calls],
    ['失败', fail],
    ['Token 用量', fmtNum(s.total_tokens) + ' <small>尽力统计</small>'],
  ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');

  $('#acctSummaryHint').textContent = `${s.per_account.length} 位老师`;
  $('#statTable').innerHTML =
    `<tr><th>老师</th><th>Key</th><th>状态</th><th class="num">调用</th><th class="num">成功</th>` +
    `<th class="num">Token</th><th>最近使用</th></tr>` +
    (s.per_account.length ? s.per_account.map(a => `<tr>
      <td>${esc(a.display_name)}</td>
      <td class="mono">${esc(a.key_prefix)}</td>
      <td>${a.enabled ? '<span class="badge on">启用</span>' : '<span class="badge off">停用</span>'}</td>
      <td class="num">${a.calls}</td><td class="num">${a.ok_calls || 0}</td>
      <td class="num">${fmtNum(a.tokens)}</td><td class="muted">${esc(a.last_used_at) || '—'}</td>
    </tr>`).join('') : emptyRow(7, '还没有老师账号'));

  $('#modelStatTable').innerHTML =
    `<tr><th>模型</th><th class="num">调用</th><th class="num">Token</th></tr>` +
    (s.per_model.length ? s.per_model.map(m => `<tr>
      <td class="mono">${esc(m.model)}</td><td class="num">${m.calls}</td>
      <td class="num">${fmtNum(m.tokens)}</td></tr>`).join('') : emptyRow(3, '暂无调用'));
}

/* ---------- 厂家 ---------- */
let PRESETS = [];
async function loadProviders() {
  if (!PRESETS.length) PRESETS = await api('GET', '/presets');
  const list = await api('GET', '/providers');
  $('#providerList').innerHTML = list.length ? '' : `<div class="panel" style="padding:28px;text-align:center" class="muted">还没有厂家，点右上角「添加厂家」开始。</div>`;
  const models = await api('GET', '/models');
  for (const p of list) {
    const mine = models.filter(m => m.provider_id === p.id);
    const el = document.createElement('div'); el.className = 'prov';
    el.innerHTML = `
      <div class="prov-top">
        <span class="pn">${esc(p.name)}</span>
        <span class="badge ${p.enabled ? 'on' : 'off'}">${p.enabled ? '启用' : '停用'}</span>
        <span class="badge off">${p.key_mask ? 'Key ' + esc(p.key_mask) : '未配置 Key'}</span>
      </div>
      <div class="prov-meta">${esc(p.base_url)}${p.note ? ' · ' + esc(p.note) : ''}</div>
      <div class="prov-models">${mine.map(m => `<span class="chip">${esc(m.public_name)}</span>`).join('') || '<span class="muted">未添加模型</span>'}</div>
      <div class="prov-actions">
        <button class="btn-mini" data-edit="${p.id}">编辑</button>
        <button class="btn-mini" data-toggle="${p.id}" data-en="${p.enabled}">${p.enabled ? '停用' : '启用'}</button>
        <button class="btn-mini" data-addm="${p.id}">+ 模型</button>
        <button class="btn-danger" data-del="${p.id}">删除</button>
      </div>`;
    $('#providerList').appendChild(el);
  }
}
$('#providerList').addEventListener('click', async e => {
  const b = e.target;
  if (b.dataset.edit) editProvider(+b.dataset.edit);
  else if (b.dataset.toggle) { await api('PUT', '/providers/' + b.dataset.toggle, { enabled: b.dataset.en !== '1' }); loadProviders(); }
  else if (b.dataset.addm) addModel(+b.dataset.addm);
  else if (b.dataset.del) {
    if (confirm('删除该厂家？其下的模型路由也会一并删除。')) { await api('DELETE', '/providers/' + b.dataset.del); toast('已删除'); loadProviders(); }
  }
});
$('#addProviderBtn').addEventListener('click', () => editProvider(null));

function presetOptions(sel) {
  return PRESETS.map(p => `<option value="${p.key}" ${p.key === sel ? 'selected' : ''}>${esc(p.label)}</option>`).join('');
}
async function editProvider(id) {
  let p = null;
  if (id) { const all = await api('GET', '/providers'); p = all.find(x => x.id === id); }
  modal(`<h3>${id ? '编辑厂家' : '添加厂家'}</h3>
    ${id ? '' : `<label>选择预设（自动填地址/模型）</label><select id="mPreset">${presetOptions(p && p.preset)}</select>`}
    <label>显示名称</label><input id="mName" value="${esc(p ? p.name : '')}" placeholder="如 DeepSeek">
    <label>Base URL（填到 /v1 级别）</label><input id="mBase" value="${esc(p ? p.base_url : '')}" placeholder="https://api.deepseek.com/v1">
    <label>API Key（真实厂家 Key${id ? '，留空=不修改' : ''}）</label><input id="mKey" type="password" placeholder="${id && p.has_key ? '已配置，留空不改' : 'sk-...'}">
    ${id ? '' : `<label>开放的模型（逗号分隔，老师将能调用）</label><input id="mModels" placeholder="deepseek-chat, deepseek-reasoner">`}
    <label>备注（可选）</label><input id="mNote" value="${esc(p ? p.note : '')}">
    <div class="acts"><button class="btn-ghost" id="mCancel">取消</button><button class="btn-primary" id="mSave">保存</button></div>`);
  if (!id) {
    const fill = () => {
      const pr = PRESETS.find(x => x.key === $('#mPreset').value);
      if (!pr) return;
      if (pr.key !== 'custom') { $('#mName').value = pr.label; $('#mBase').value = pr.base_url; $('#mModels').value = (pr.models || []).join(', '); }
    };
    $('#mPreset').addEventListener('change', fill); if (!p) fill();
  }
  $('#mCancel').onclick = closeModal;
  $('#mSave').onclick = async () => {
    const name = $('#mName').value.trim(), base = $('#mBase').value.trim();
    if (!name || !base) return toast('名称和 Base URL 必填');
    try {
      if (id) {
        const patch = { name, base_url: base, note: $('#mNote').value };
        if ($('#mKey').value.trim()) patch.api_key = $('#mKey').value.trim();
        await api('PUT', '/providers/' + id, patch);
      } else {
        await api('POST', '/providers', {
          name, base_url: base, preset: $('#mPreset').value, api_key: $('#mKey').value.trim(),
          note: $('#mNote').value, models: $('#mModels').value.split(',').map(s => s.trim()).filter(Boolean),
        });
      }
      closeModal(); toast('已保存'); loadProviders();
    } catch (err) { toast(err.message); }
  };
}

/* ---------- 模型路由 ---------- */
async function loadModels() {
  const list = await api('GET', '/models');
  $('#modelTable').innerHTML =
    `<tr><th>对外模型名</th><th>厂家</th><th>上游模型</th><th>状态</th><th></th></tr>` +
    (list.length ? list.map(m => `<tr>
      <td class="mono">${esc(m.public_name)}</td>
      <td>${esc(m.provider_name)}${m.provider_enabled ? '' : ' <span class="muted">(厂家停用)</span>'}</td>
      <td class="mono">${esc(m.upstream_model)}</td>
      <td>${m.enabled ? '<span class="badge on">启用</span>' : '<span class="badge off">停用</span>'}</td>
      <td><button class="btn-mini" data-mtoggle="${m.id}" data-en="${m.enabled}">${m.enabled ? '停用' : '启用'}</button>
          <button class="btn-danger" data-mdel="${m.id}">删除</button></td>
    </tr>`).join('') : emptyRow(5, '还没有模型，去「厂家」里添加'));
}
$('#modelTable').addEventListener('click', async e => {
  const b = e.target;
  if (b.dataset.mtoggle) { await api('PUT', '/models/' + b.dataset.mtoggle, { enabled: b.dataset.en !== '1' }); loadModels(); }
  else if (b.dataset.mdel) { if (confirm('删除该模型路由？')) { await api('DELETE', '/models/' + b.dataset.mdel); loadModels(); } }
});
$('#addModelBtn').addEventListener('click', () => addModel(null));

async function addModel(providerId) {
  const provs = await api('GET', '/providers');
  if (!provs.length) return toast('请先添加厂家');
  modal(`<h3>添加模型</h3>
    <label>所属厂家</label><select id="aProv">${provs.map(p => `<option value="${p.id}" ${p.id === providerId ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select>
    <label>对外模型名（老师在客户端填这个）</label><input id="aPub" placeholder="deepseek-chat">
    <label>上游真实模型名（留空=同上）</label><input id="aUp" placeholder="可做别名">
    <label>备注（可选）</label><input id="aNote">
    <div class="acts"><button class="btn-ghost" id="aCancel">取消</button><button class="btn-primary" id="aSave">添加</button></div>`);
  $('#aCancel').onclick = closeModal;
  $('#aSave').onclick = async () => {
    const pub = $('#aPub').value.trim();
    if (!pub) return toast('对外模型名必填');
    try {
      await api('POST', '/models', { public_name: pub, provider_id: +$('#aProv').value,
        upstream_model: $('#aUp').value.trim(), note: $('#aNote').value });
      closeModal(); toast('已添加'); loadModels(); loadProviders();
    } catch (err) { toast(err.message); }
  };
}

/* ---------- 老师账号 ---------- */
async function loadAccounts() {
  const list = await api('GET', '/accounts');
  $('#accountTable').innerHTML =
    `<tr><th>姓名</th><th>手机号</th><th>登录</th><th>Key</th><th>状态</th><th class="num">已用</th><th>限额</th><th></th></tr>` +
    (list.length ? list.map(a => `<tr>
      <td>${esc(a.display_name)}${a.note ? ' <span class="muted">·' + esc(a.note) + '</span>' : ''}</td>
      <td class="mono">${esc(a.phone) || '<span class="muted">—</span>'}</td>
      <td>${a.has_login ? (a.must_change_pwd ? '<span class="badge off">待改密</span>' : '<span class="badge on">已设</span>') : '<span class="muted">无</span>'}</td>
      <td class="mono">${esc(a.key_prefix)}</td>
      <td><span class="badge ${a.enabled ? 'on' : 'off'} toggle" data-atoggle="${a.id}" data-en="${a.enabled}">${a.enabled ? '启用' : '停用'}</span></td>
      <td class="num">${a.quota_used}</td>
      <td>${a.quota_total ? a.quota_used + ' / ' + a.quota_total : '不限'}</td>
      <td>
        <button class="btn-mini" data-aedit="${a.id}">编辑</button>
        ${a.phone ? `<button class="btn-mini" data-apwd="${a.id}">重置密码</button>` : ''}
        <button class="btn-mini" data-akey="${a.id}">重置Key</button>
        <button class="btn-danger" data-adel="${a.id}">删除</button>
      </td></tr>`).join('') : emptyRow(8, '还没有老师，点「新建老师」或「批量导入」'));
}
$('#accountTable').addEventListener('click', async e => {
  const b = e.target;
  if (b.dataset.atoggle) { await api('PUT', '/accounts/' + b.dataset.atoggle, { enabled: b.dataset.en !== '1' }); loadAccounts(); }
  else if (b.dataset.aedit) editAccount(+b.dataset.aedit);
  else if (b.dataset.apwd) { if (confirm('把该老师的登录密码重置为默认密码 openkeyhub？老师下次登录需重新改密。')) { await api('POST', `/accounts/${b.dataset.apwd}/reset-login`); toast('已重置为默认密码 openkeyhub'); loadAccounts(); } }
  else if (b.dataset.akey) { if (confirm('重置后旧 Key 立即失效，老师需重新登录老师端获取新 Key。继续？')) { const r = await api('POST', `/accounts/${b.dataset.akey}/reset-key`); showKeys('新的 Key', [{ display_name: '新 Key', api_key: r.api_key }]); loadAccounts(); } }
  else if (b.dataset.adel) { if (confirm('删除该老师账号？其 Key 立即失效。')) { await api('DELETE', '/accounts/' + b.dataset.adel); loadAccounts(); } }
});
$('#addAccountBtn').addEventListener('click', () => addAccount());
$('#importBtn').addEventListener('click', () => importAccounts());

function quotaFields(a) {
  return `<div class="row">
      <div><label>调用次数上限（0=不限）</label><input id="qTotal" type="number" min="0" value="${a ? a.quota_total : 0}"></div>
      <div><label>每分钟限速（0=不限）</label><input id="qRate" type="number" min="0" value="${a ? a.rate_per_min : 0}"></div>
    </div>`;
}
function addAccount() {
  modal(`<h3>新建老师</h3>
    <label>姓名 / 标识</label><input id="acName" placeholder="如 张老师 / 数学组">
    <label>手机号（老师端登录账号，可空）</label><input id="acPhone" placeholder="填了即开通老师自助登录">
    <label>备注（可选）</label><input id="acNote" placeholder="工号、学科等">
    ${quotaFields(null)}
    <div class="acts"><button class="btn-ghost" id="acCancel">取消</button><button class="btn-primary" id="acSave">创建并生成 Key</button></div>`);
  $('#acCancel').onclick = closeModal;
  $('#acSave').onclick = async () => {
    const name = $('#acName').value.trim();
    if (!name) return toast('姓名必填');
    try {
      const r = await api('POST', '/accounts', { display_name: name, phone: $('#acPhone').value.trim(),
        note: $('#acNote').value, quota_total: +$('#qTotal').value || 0, rate_per_min: +$('#qRate').value || 0 });
      showKeys('账号已创建', [{ display_name: name, phone: $('#acPhone').value.trim(), api_key: r.api_key }]); loadAccounts();
    } catch (err) { toast(err.message); }
  };
}
async function editAccount(id) {
  const all = await api('GET', '/accounts'); const a = all.find(x => x.id === id); if (!a) return;
  modal(`<h3>编辑老师</h3>
    <label>姓名 / 标识</label><input id="acName" value="${esc(a.display_name)}">
    <label>手机号（老师端登录账号）</label><input id="acPhone" value="${esc(a.phone)}" placeholder="填了即开通老师自助登录">
    <label>备注</label><input id="acNote" value="${esc(a.note)}">
    ${quotaFields(a)}
    <div class="acts"><button class="btn-ghost" id="acCancel">取消</button><button class="btn-primary" id="acSave">保存</button></div>`);
  $('#acCancel').onclick = closeModal;
  $('#acSave').onclick = async () => {
    try {
      await api('PUT', '/accounts/' + id, { display_name: $('#acName').value.trim(), phone: $('#acPhone').value.trim(),
        note: $('#acNote').value, quota_total: +$('#qTotal').value || 0, rate_per_min: +$('#qRate').value || 0 });
      closeModal(); toast('已保存'); loadAccounts();
    } catch (err) { toast(err.message); }
  };
}
function importAccounts() {
  modal(`<h3>批量导入老师</h3>
    <label>每行一位：<b>姓名,手机号</b> 或 <b>姓名,手机号,备注</b>（支持 CSV，手机号可空）</label>
    <textarea id="impText" rows="7" placeholder="张老师,13800000001,语文&#10;李老师,13800000002,数学&#10;王老师,13800000003"></textarea>
    <p class="muted">填了手机号的老师可在「老师端」用手机号 + 默认密码 <b>openkeyhub</b> 登录，自助查看 Key。</p>
    ${quotaFields(null)}
    <div class="acts"><button class="btn-ghost" id="impCancel">取消</button><button class="btn-primary" id="impSave">批量生成</button></div>`);
  $('#impCancel').onclick = closeModal;
  $('#impSave').onclick = async () => {
    const text = $('#impText').value.trim();
    if (!text) return toast('请粘贴名单');
    try {
      const r = await api('POST', '/accounts/import', { text,
        quota_total: +$('#qTotal').value || 0, rate_per_min: +$('#qRate').value || 0 });
      if (r.skipped && r.skipped.length) toast(`导入 ${r.count} 位，跳过 ${r.skipped.length} 位（手机号重复等）`);
      showKeys(`成功导入 ${r.count} 位老师`, r.accounts); loadAccounts();
    } catch (err) { toast(err.message); }
  };
}
function showKeys(title, accounts) {
  const portal = location.origin + '/portal';
  const csv = 'data:text/csv;charset=utf-8,' + encodeURIComponent(
    '姓名,手机号,API Key\n' + accounts.map(a => `${a.display_name},${a.phone || ''},${a.api_key}`).join('\n'));
  const hasPhone = accounts.some(a => a.phone);
  modal(`<h3>${esc(title)}</h3>
    ${hasPhone ? `<p class="muted">填了手机号的老师可直接去 <b>老师端</b> 自助查看 Key，无需你单独分发：<br><span class="mono">${esc(portal)}</span> · 默认密码 <b>openkeyhub</b>（首登强制改密）。</p>` : `<p class="muted">把下面的 Key 连同服务地址发给对应老师。<b>Key 只显示这一次。</b></p>`}
    ${accounts.map(a => `<div class="keybox"><div class="muted">${esc(a.display_name)}${a.phone ? ' · ' + esc(a.phone) : ''}</div><div class="k">${esc(a.api_key)}</div></div>`).join('')}
    <div class="keybox" style="background:rgba(52,199,89,.08);border-color:rgba(52,199,89,.25)">
      <div class="muted">OpenAI 兼容客户端的 Base URL 填：</div>
      <div class="k" style="color:#248a3d">${esc(location.origin)}/v1</div></div>
    <div class="acts">
      <a class="btn-ghost" href="${csv}" download="老师Key名单.csv" style="text-align:center;text-decoration:none;padding:11px;border-radius:980px">下载 CSV</a>
      <button class="btn-primary" id="kOk">完成</button></div>`);
  $('#kOk').onclick = closeModal;
}

/* ---------- 日志 ---------- */
async function loadLogs() {
  const list = await api('GET', '/logs?limit=200');
  $('#logTable').innerHTML =
    `<tr><th>时间</th><th>老师</th><th>模型</th><th>状态</th><th class="num">Token</th><th class="num">耗时</th></tr>` +
    (list.length ? list.map(l => `<tr>
      <td class="muted">${esc(l.created_at)}</td>
      <td>${esc(l.display_name) || '—'}</td>
      <td class="mono">${esc(l.model)}</td>
      <td>${l.status === 'ok' ? '<span class="badge on">成功</span>' : `<span class="badge off">失败 ${l.http_code || ''}</span>`}</td>
      <td class="num">${(l.prompt_tokens + l.completion_tokens) || '—'}</td>
      <td class="num muted">${l.latency_ms} ms</td>
    </tr>`).join('') : emptyRow(6, '暂无调用记录'));
}
$('#refreshLogs').addEventListener('click', loadLogs);

/* ---------- 在线更新 ---------- */
let UPD_POLL = null;
function updShow(id, on) { $(id).classList.toggle('hidden', !on); }
function updMsg(t, kind) { const e = $('#updMsg'); e.textContent = t || ''; e.className = 'hint' + (kind ? ' ' + kind : ''); }

async function loadUpdate() {
  clearInterval(UPD_POLL); UPD_POLL = null;
  updShow('#updDownload', false); updShow('#updApply', false); updShow('#updBarWrap', false);
  $('#updNotes').innerHTML = ''; updMsg('');
  let st;
  try { st = await api('GET', '/update/status'); } catch (e) { updMsg(e.message, 'err'); return; }
  $('#updCurVer').textContent = 'v' + st.version;
  // 只显示管理员自填的源；内置官方源地址隐藏（不暴露服务器地址）。
  $('#updUrl').value = st.update_url || '';
  const srcHint = (st.source_ready && !st.update_url)
    ? '正在使用内置的官方更新源（地址已隐藏）。如自行部署，可在上方填写你自己的更新源并保存。'
    : (st.source_ready ? '' : '尚未配置更新源：请在上方填写更新源地址（含 version.json）并保存。');
  const modeHint = st.portable
    ? '当前为免安装包模式，支持一键重启升级。'
    : '当前为开发/源码模式，仅能检查与下载，不执行自动替换（请手动更新代码）。';
  $('#updEnvHint').textContent = (srcHint ? srcHint + ' ' : '') + modeHint;
  if (st.state === 'downloading') { beginPoll(); }
  else if (st.pending || st.state === 'ready') { updShow('#updApply', st.portable); updMsg(st.msg || '新版已就绪，可重启升级。', 'ok'); }
}

$('#updSaveSrc').addEventListener('click', async () => {
  try { await api('POST', '/update/source', { update_url: $('#updUrl').value.trim() }); toast('更新源已保存'); }
  catch (e) { toast(e.message); }
});

$('#updCheck').addEventListener('click', async () => {
  updMsg('正在检查…'); $('#updNotes').innerHTML = ''; updShow('#updDownload', false); updShow('#updApply', false);
  let r; try { r = await api('POST', '/update/check'); } catch (e) { updMsg(e.message, 'err'); return; }
  if (!r.ok) { updMsg(r.msg || '检查失败', 'err'); return; }
  if (!r.newer) { updMsg(`已是最新版本 v${r.current}`, 'ok'); return; }
  updMsg(`发现新版本 v${r.latest}（当前 v${r.current}${r.size ? '，约 ' + (r.size / 1048576).toFixed(1) + ' MB' : ''}）`, 'ok');
  if (r.notes) $('#updNotes').innerHTML = `<div class="upd-notes-h">更新内容</div><pre>${esc(r.notes)}</pre>`;
  updShow('#updDownload', true);
});

$('#updDownload').addEventListener('click', async () => {
  updShow('#updDownload', false);
  try { await api('POST', '/update/download'); } catch (e) { updMsg(e.message, 'err'); updShow('#updDownload', true); return; }
  beginPoll();
});

function beginPoll() {
  updShow('#updBarWrap', true);
  clearInterval(UPD_POLL);
  UPD_POLL = setInterval(async () => {
    let st; try { st = await api('GET', '/update/status'); } catch (e) { return; }
    $('#updBar').style.width = (st.pct || 0) + '%';
    updMsg(st.msg || '', st.state === 'error' ? 'err' : '');
    if (st.state === 'error') { clearInterval(UPD_POLL); updShow('#updBarWrap', false); updShow('#updDownload', true); }
    else if (st.state === 'ready') {
      clearInterval(UPD_POLL); updShow('#updBarWrap', false);
      if (st.portable) { updShow('#updApply', true); updMsg(st.msg || '新版已就绪，点击「重启完成升级」', 'ok'); }
      else { updMsg('新版已下载到数据目录 updates/，请手动替换代码后重启。', 'ok'); }
    }
  }, 800);
}

$('#updApply').addEventListener('click', async () => {
  if (!confirm('确定重启并完成升级？服务会短暂中断约 10 秒。')) return;
  updShow('#updApply', false); updMsg('正在重启升级，约 10 秒后自动刷新…');
  try { await api('POST', '/update/apply'); } catch (e) { /* 主进程会退出，请求可能不返回，正常 */ }
  let tries = 0;
  const wait = setInterval(async () => {
    tries++;
    try { const h = await fetch('/health'); if (h.ok) { clearInterval(wait); location.reload(); } }
    catch (e) {}
    if (tries > 40) { clearInterval(wait); updMsg('升级完成后请手动刷新页面。', 'ok'); }
  }, 1500);
});

/* ---------- 工具 ---------- */
function emptyRow(cols, text) { return `<tr><td colspan="${cols}" style="text-align:center;padding:30px" class="muted">${text}</td></tr>`; }
function fmtNum(n) { n = +n || 0; return n >= 10000 ? (n / 10000).toFixed(1) + 'w' : String(n); }

boot();
