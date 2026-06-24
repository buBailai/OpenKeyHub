'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function api(path, body) {
  const opt = { method: body ? 'POST' : 'GET', headers: {}, credentials: 'same-origin' };
  if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch('/api/portal' + path, opt);
  let data = null; try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((data && data.detail) || ('错误 ' + r.status));
  return data;
}
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add('hidden'), 2200);
}
function show(view) {
  ['vLogin', 'vChange', 'vKey'].forEach(v => $('#' + v).classList.toggle('hidden', v !== view));
}

async function boot() {
  try {
    const st = await api('/state');
    if (!st.logged_in) return show('vLogin');
    if (st.must_change_pwd) return show('vChange');
    await loadKey();
  } catch (e) { show('vLogin'); }
}

$('#loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const phone = $('#pPhone').value.trim(), password = $('#pPass').value;
  const h = $('#pHint'); h.textContent = ''; h.className = 'hint';
  if (!phone || !password) { h.textContent = '请输入手机号和密码'; h.classList.add('err'); return; }
  try {
    const r = await api('/login', { phone, password });
    if (r.must_change_pwd) { $('#cOld').value = password; show('vChange'); }
    else await loadKey();
  } catch (err) { h.textContent = err.message; h.classList.add('err'); }
});

$('#changeForm').addEventListener('submit', async e => {
  e.preventDefault();
  const oldp = $('#cOld').value, np = $('#cNew').value, np2 = $('#cNew2').value;
  const h = $('#cHint'); h.textContent = ''; h.className = 'hint';
  if (np.length < 6) { h.textContent = '新密码至少 6 位'; h.classList.add('err'); return; }
  if (np !== np2) { h.textContent = '两次输入的新密码不一致'; h.classList.add('err'); return; }
  try {
    await api('/change-password', { old_password: oldp, new_password: np });
    toast('密码已更新');
    await loadKey();
  } catch (err) { h.textContent = err.message; h.classList.add('err'); }
});

async function loadKey() {
  const d = await api('/key');
  $('#kName').textContent = d.display_name + ' 的密钥';
  $('#kBase').textContent = d.base_url;
  $('#kKey').textContent = d.api_key;
  $('#kModels').innerHTML = d.models.length
    ? d.models.map(m => `<span class="chip">${esc(m)}</span>`).join('')
    : '<span class="muted">管理员暂未开放模型，请联系学校</span>';
  $('#kHow').innerHTML = `在支持 OpenAI 接口的客户端里，把厂商 / 接口类型选成「OpenAI 兼容」或「自定义」，Base URL 和 API Key 填上面两项，模型填上方任一，保存即可使用。`;
  if (!d.enabled) toast('你的账号已被停用，暂时无法调用');
  show('vKey');
}

document.addEventListener('click', e => {
  const id = e.target.dataset && e.target.dataset.copy;
  if (id) {
    const txt = $('#' + id).textContent;
    navigator.clipboard.writeText(txt).then(() => toast('已复制')).catch(() => toast('复制失败，请手动选择'));
  }
});
$('#pLogout').addEventListener('click', async () => { await api('/logout', {}); location.reload(); });
$('#pChangePwd').addEventListener('click', () => { $('#cOld').value = ''; $('#cNew').value = ''; $('#cNew2').value = ''; show('vChange'); });

boot();
