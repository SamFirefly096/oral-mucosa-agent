return {
  inject: ['shell', 'fs', 'webServer'],
  apply(ctx) {
    const shell = ctx.shell
    const fs = ctx.fs
    const webServer = ctx.webServer
    const base = '/opt/oral-mucosa-agent'
    const ROOT = base + '/.docflow'
    const PY = ROOT + '/venv/bin/python'
    const ENGINE = ROOT + '/engine/docflow_engine.py'
    const UPLOADS = ROOT + '/uploads'
    const OUTPUTS = ROOT + '/outputs'
    const MAX_BYTES = 100 * 1024 * 1024
    const UPLOAD_MAX_B64 = 125 * 1024 * 1024

    const files = new Map()
    let seq = 0
    const metaByUser = new Map()
    // ── 多用户隔离 ──
    // nginx 在 X-Forwarded-User 头携带登录名（dsh=管理员）。会话归属按 cwd：
    // /home/<用户名>/ 下属于该用户，其余属于管理员（与 dsh-host-apiproxy 补丁一致）。
    // 管理员沿用 /opt/oral-mucosa-agent/.docflow；普通用户使用 /home/<用户名>/.docflow。
    // 动态插件（harness RPC）拿不到 HTTP 头：RPC 处理器从 args.user 取（缺省管理员），
    // 工具从 exec.agent.session.header.cwd 推断。
    const ADMIN_USER = 'dsh'
    function normUser(u) {
      const s = String(u || '').trim()
      return /^[a-zA-Z0-9_-]{1,32}$/.test(s) ? s : ADMIN_USER
    }
    function harnessUser(a) {
      return normUser(a && a.user)
    }
    function userOfCwd(cwd) {
      if (typeof cwd !== 'string' || !cwd) return ADMIN_USER
      const m = /^\/home\/([^/]+)\//.exec(cwd)
      return m ? normUser(m[1]) : ADMIN_USER
    }
    function userOfExec(exec) {
      try {
        const s = exec && exec.agent && exec.agent.session
        return userOfCwd(s && s.header && s.header.cwd)
      } catch (e) {
        return ADMIN_USER
      }
    }
    function userRoot(user) {
      return user === ADMIN_USER ? base : '/home/' + user
    }
    function docRoot(user) {
      return userRoot(user) + '/.docflow'
    }
    function uploadsOf(user) {
      return docRoot(user) + '/uploads'
    }
    function outputsOf(user) {
      return docRoot(user) + '/outputs'
    }
    function policyOf(user) {
      return { mode: 'workspace-write', workspaceRoot: userRoot(user) }
    }
    function metaOfUser(user) {
      let m = metaByUser.get(user)
      if (!m) {
        m = {}
        metaByUser.set(user, m)
      }
      return m
    }
    function fileOf(id, user) {
      const info = files.get(id)
      return info && info.user === user ? info : undefined
    }

    async function loadMeta(user) {
      // 主文件缺失/损坏时回退到 .bak（保存时同步写的双副本）
      const p = docRoot(user) + '/meta.json'
      try {
        const raw = await fs.readText(await fs.resolve(p))
        if (raw) {
          metaByUser.set(user, JSON.parse(raw) || {})
          return
        }
      } catch (e) {}
      try {
        const raw = await fs.readText(await fs.resolve(p + '.bak'))
        if (raw) metaByUser.set(user, JSON.parse(raw) || {})
      } catch (e) {}
    }
    async function saveMeta(user) {
      try {
        const body = JSON.stringify(metaOfUser(user))
        const p = docRoot(user) + '/meta.json'
        await fs.writeText(await fs.resolve(p), body, undefined, undefined, policyOf(user))
        await fs.writeText(await fs.resolve(p + '.bak'), body, undefined, undefined, policyOf(user))
      } catch (e) {}
    }
    function fmtTime(ts) {
      if (!ts) return ''
      const d = new Date(ts)
      const p = (n) => (n < 10 ? '0' + n : '' + n)
      return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes())
    }
    function opsSummary(ops) {
      const names = { replace: '查找替换', 'set-title': '改标题', append: '追加内容', restyle: '换主题色' }
      const cnt = {}
      for (const op of ops || []) {
        const n = names[op && op.type] || (op && op.type) || '编辑'
        cnt[n] = (cnt[n] || 0) + 1
      }
      const parts = Object.keys(cnt).map((k) => (cnt[k] > 1 ? k + '×' + cnt[k] : k))
      return parts.join(' · ') || '修改文档'
    }

    // fs/shell 的默认沙箱策略工作区根是 /root，本会话工作区在 /opt/oral-mucosa-agent，
    // 所有写操作必须显式声明 workspace-write + 工作区根
    const POLICY = { mode: 'workspace-write', workspaceRoot: base }

    function q(s) {
      return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$').replace(/`/g, '\\`') + '"'
    }
    function sanitize(name) {
      let s = String(name == null ? 'file' : name)
        .replace(/[\s\\\/:*?"<>|\x00-\x1f]/g, '_')
        .replace(/^\.+/, '')
        .replace(/_+/g, '_')
      if (s.length > 90) s = s.slice(0, 90)
      return s || 'file'
    }
    function extOf(name) {
      const m = /\.([A-Za-z0-9]+)$/.exec(String(name))
      return m ? m[1].toLowerCase() : ''
    }
    function fmtOf(name) {
      const e = extOf(name)
      if (e === 'markdown') return 'md'
      return ['docx', 'pptx', 'ppt', 'pdf', 'txt', 'md', 'xlsx', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].indexOf(e) >= 0 ? e : 'file'
    }
    function catOf(name) {
      const m = /^【(.+?)】/.exec(String(name || ''))
      return m ? m[1].trim() : ''
    }
    function stripCat(name) {
      return String(name || '').replace(/^【.+?】/, '')
    }
    function applyCat(name, cat) {
      const s = sanitize(name)
      const c = String(cat || '').trim()
      if (!c) return s
      if (catOf(s)) return s
      return '【' + sanitize(c) + '】' + s
    }
    function normCat(c) {
      return c || '未分类'
    }
    function newId(kind) { return kind + '_' + Date.now().toString(36) + '_' + (seq++).toString(36) }
    // 下载地址用相对路径：浏览器会按当前页面 origin 解析，
    // 用户通过任意地址（127.0.0.1 / 服务器IP / 域名 / 端口转发）访问 GUI 均可下载
    function urlOf(id) { return '/dsh-docflow/download/' + id }
    function kb(n) { return ((n || 0) / 1024).toFixed(1) + ' KB' }
    function pct(s) {
      const bytes = new TextEncoder().encode(String(s))
      let out = ''
      for (let i = 0; i < bytes.length; i++) {
        const b = bytes[i]
        if ((b >= 0x41 && b <= 0x5A) || (b >= 0x61 && b <= 0x7A) || (b >= 0x30 && b <= 0x39) || b === 0x2D || b === 0x2E || b === 0x5F || b === 0x7E) out += String.fromCharCode(b)
        else out += '%' + (b < 16 ? '0' : '') + b.toString(16).toUpperCase()
      }
      return out
    }
    const MIME = {
      docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      ppt: 'application/vnd.ms-powerpoint',
      pdf: 'application/pdf',
      txt: 'text/plain; charset=utf-8',
      md: 'text/markdown; charset=utf-8',
      xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      png: 'image/png',
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
      gif: 'image/gif',
      webp: 'image/webp',
      bmp: 'image/bmp',
      svg: 'image/svg+xml',
    }

    function pick(info, user) {
      const m = metaOfUser(user)[info.id] || {}
      return {
        fileId: info.id,
        name: info.name,
        kind: info.kind,
        size: info.size || 0,
        format: info.format,
        category: m.category || '',
        createdAt: info.createdAt,
        downloadUrl: urlOf(info.id),
        direction: m.direction || (info.kind === 'uploads' ? 'upload' : 'output'),
        mtime: fmtTime(info.fileMtime || info.createdAt) || m.mtime || '',
        request: m.request || '',
        summary: m.summary || '',
      }
    }

    async function runPy(args, stdin, user) {
      try {
        const spec = shell.resolve({
          command: PY + ' ' + ENGINE + ' ' + args,
          workdir: ROOT,
          timeoutMs: 240000,
          stdoutMaxBytes: 64 * 1024 * 1024,
          stdin: stdin,
          sandboxPolicy: policyOf(user),
        })
        const res = await shell.run(spec)
        return res
      } catch (e) {
        return { exitCode: -1, stdout: '', stderr: String((e && e.message) || e) }
      }
    }
    // 把 JSON 数据写入临时文件，返回其路径（绕开 stdin 传递的不确定性）
    async function writeJsonTemp(payload, user) {
      const tmpPath = docRoot(user) + '/tmp/spec_' + newId('t') + '.json'
      await fs.writeText(await fs.resolve(tmpPath), typeof payload === 'string' ? payload : JSON.stringify(payload), undefined, undefined, policyOf(user))
      return tmpPath
    }
    // 带 spec 文件执行 create/edit：数据落盘后把路径作为最后一个参数
    async function runPySpec(sub, fmt, outPath, extraPath, payload, user) {
      const specPath = await writeJsonTemp(payload, user)
      let args = sub + ' ' + fmt + ' ' + q(outPath)
      if (extraPath) args += ' ' + q(extraPath)
      args += ' ' + q(specPath)
      return runPy(args, null, user)
    }
    // 把 JSON 数据写入临时文件，再执行一个引擎命令（参数以文件路径追加）
    async function runPyJson(sub, payload, extraArgs, user) {
      const jsonPath = await writeJsonTemp(payload, user)
      let args = sub + ' ' + q(jsonPath)
      if (extraArgs) args += ' ' + extraArgs
      return runPy(args, null, user)
    }
    // DSH 新版 shell 服务：stdout/stderr 为 CollectedOutput 对象 {text, truncated, spillPath}，
    // 旧版为纯字符串；两种形状都兼容
    function outText(v) {
      if (typeof v === 'string') return v
      if (v && typeof v === 'object' && typeof v.text === 'string') return v.text
      return ''
    }
    function errOf(res, n) {
      const s = outText(res && res.stderr) || outText(res && res.stdout)
      return s.slice(0, n || 400)
    }
    function parseResult(res) {
      try { return JSON.parse(outText(res && res.stdout)) } catch (e) { return null }
    }

    // ---------- 文献检索 / 核查（真实来源：PubMed E-utilities + Crossref） ----------
    async function handleLitSearch(args) {
      const term = String(args.term || '').trim()
      if (!term) return { ok: false, error: '缺少检索词 term' }
      const retmax = Math.min(Math.max(parseInt(args.maxResults, 10) || 8, 1), 20)
      const res = await runPy('lit-search ' + q(term) + ' ' + retmax, null, ADMIN_USER)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: '检索失败: ' + errOf(res) }
      return { ok: true, count: j.count, items: j.items || [] }
    }

    async function handleLitCrossref(args) {
      const query = String(args.query || '').trim()
      if (!query) return { ok: false, error: '缺少查询词 query' }
      const rows = Math.min(Math.max(parseInt(args.maxResults, 10) || 5, 1), 10)
      const res = await runPy('lit-crossref ' + q(query) + ' ' + rows, null, ADMIN_USER)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: 'Crossref 检索失败: ' + errOf(res) }
      return { ok: true, items: j.items || [] }
    }

    async function handleLitVerify(args) {
      const refs = args.references
      if (!Array.isArray(refs) || !refs.length) return { ok: false, error: '缺少 references 数组' }
      const res = await runPyJson('lit-verify', refs, null, ADMIN_USER)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: '核查失败: ' + errOf(res) }
      return { ok: true, results: j.results || [] }
    }

    ctx.effect(() => harness.handle('lit-search', (a) => handleLitSearch(a)))
    ctx.effect(() => harness.handle('lit-crossref', (a) => handleLitCrossref(a)))
    ctx.effect(() => harness.handle('lit-verify', (a) => handleLitVerify(a)))

    // ---------- 图片搜索 / 识别 ----------
    async function handleImageSearch(args) {
      const query = String(args.query || '').trim()
      if (!query) return { ok: false, error: '缺少搜索词 query' }
      const max = Math.min(Math.max(parseInt(args.maxResults, 10) || 5, 1), 20)
      const type = ['photo', 'vector', 'all'].indexOf(args.type) >= 0 ? args.type : 'all'
      const res = await runPy('image-search ' + q(query) + ' ' + max + ' ' + q(type), null, ADMIN_USER)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: '图片搜索失败: ' + errOf(res) }
      return { ok: true, items: j.items || [] }
    }

    async function handleImageRecognize(args) {
      const user = harnessUser(args)
      let path = ''
      if (args.fileId) {
        const info = fileOf(args.fileId, user)
        if (!info) return { ok: false, error: '文件不存在' }
        path = info.path
      } else if (args.path) {
        path = String(args.path)
      } else {
        return { ok: false, error: '需要 fileId 或 path' }
      }
      const res = await runPy('image-recognize ' + q(path), null, user)
      const j = parseResult(res)
      if (!j || !j.ok) return { ok: false, error: '识别失败: ' + errOf(res) }
      return { ok: true, info: j.info || {}, ocr: j.ocr || '', description: j.description || '', vision_error: j.vision_error || '' }
    }

    ctx.effect(() => harness.handle('image-search', (a) => handleImageSearch(a)))
    ctx.effect(() => harness.handle('image-recognize', (a) => handleImageRecognize(a)))

    async function ensureDirs(user) {
      try {
        const spec = shell.resolve({ command: 'mkdir -p ' + q(uploadsOf(user)) + ' ' + q(outputsOf(user)) + ' ' + q(docRoot(user) + '/tmp'), workdir: userRoot(user), timeoutMs: 30000, sandboxPolicy: policyOf(user) })
        await shell.run(spec)
      } catch (e) {}
    }

    // DSH 的 fs.stat 不返回 mtime，shell stat 又受沙箱限制；经引擎取磁盘真实修改时间
    async function dirMtimes(dir, user) {
      try {
        const res = await runPy('dir-mtimes ' + q(dir), null, user)
        const j = parseResult(res)
        return j && typeof j === 'object' && !Array.isArray(j) ? j : {}
      } catch (e) {
        return {}
      }
    }
    async function scanDir(dir, kind, user) {
      try {
        const target = await fs.resolve(dir)
        const entries = await fs.listDir(target)
        const mtMap = await dirMtimes(dir, user)
        let metaDirty = false
        for (const e of entries) {
          if (e.type !== 'file') continue
          // 合法文件名：<u|o>_<base36>_<seq>__<原名>，例如 o_rvw001_0__报告.docx
          const m = /^([ou]_[a-z0-9]+(?:_[a-z0-9]+)?)__(.+)$/.exec(e.name)
          if (!m) continue
          const id = m[1]
          if (files.has(id)) continue
          const full = dir + '/' + e.name
          // 修改时间以磁盘文件真实 mtime 为准（重启后不再重置为启动时间）
          const realMt = mtMap[full] || 0
          files.set(id, {
            id: id,
            name: m[2],
            kind: kind,
            user: user,
            path: full,
            size: e.size || 0,
            format: fmtOf(m[2]),
            createdAt: realMt || Date.now(),
            fileMtime: realMt || Date.now(),
          })
          const um = metaOfUser(user)
          if (!um[id]) {
            um[id] = { direction: kind === 'uploads' ? 'upload' : 'output', mtime: fmtTime(realMt || Date.now()), request: '', summary: '' }
            metaDirty = true
          } else if (realMt && um[id].mtime !== fmtTime(realMt)) {
            // 校正历史错误记录（旧版曾把重启时间写进 meta）
            um[id].mtime = fmtTime(realMt)
            metaDirty = true
          }
          // 旧数据迁移：从文件名【分类】前缀推断分类
          if (!um[id].category) {
            const c = catOf(m[2])
            if (c) {
              um[id].category = c
              metaDirty = true
            }
          }
        }
        if (metaDirty) saveMeta(user)
      } catch (e) {}
    }

    function countOf(kind, user) {
      let n = 0
      files.forEach((f) => { if (f.kind === kind && f.user === user) n++ })
      return n
    }

    ensureDirs(ADMIN_USER).then(() => loadMeta(ADMIN_USER).then(() => Promise.all([scanDir(UPLOADS, 'uploads', ADMIN_USER), scanDir(OUTPUTS, 'outputs', ADMIN_USER)]))).catch(() => {})

    ctx.effect(() => webServer.register({
      kind: 'prefix',
      path: '/dsh-docflow/download',
      handler: async (req, res) => {
        try {
          let user = ADMIN_USER
          try {
            const v = req && req.headers && req.headers['x-forwarded-user']
            user = normUser(typeof v === 'string' ? v : '')
          } catch (e) {}
          const tail = (req.url || '').split('?')[0].split('/').pop() || ''
          const info = fileOf(tail, user)
          if (!info) {
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
            res.end('文件不存在或已过期')
            return
          }
          const target = await fs.resolve(info.path)
          let bytes
          try {
            bytes = await fs.readBytes(target, undefined, MAX_BYTES)
          } catch (e) {
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
            res.end('文件读取失败')
            return
          }
          res.writeHead(200, {
            'Content-Type': MIME[info.format] || 'application/octet-stream',
            'Content-Length': String(bytes.length),
            'Content-Disposition': 'attachment; filename="download.' + info.format + '"; filename*=UTF-8\'\'' + pct(info.name),
            'Cache-Control': 'no-store',
          })
          res.end(bytes)
        } catch (e) {
          try {
            res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
            res.end('服务器错误')
          } catch (e2) {}
        }
      },
    }))

    async function userInit(user) {
      await ensureDirs(user)
      await loadMeta(user)
    }

    async function handleStatus(args) {
      const user = harnessUser(args)
      await userInit(user)
      await scanDir(uploadsOf(user), 'uploads', user)
      await scanDir(outputsOf(user), 'outputs', user)
      let engineReady = false
      try {
        const st = await fs.stat(await fs.resolve(ENGINE))
        engineReady = !!(st && st.type === 'file')
      } catch (e) {}
      return {
        ok: true,
        engineReady: engineReady,
        root: docRoot(user),
        user: user,
        downloadBase: urlOf(''),
        counts: { uploads: countOf('uploads', user), outputs: countOf('outputs', user) },
      }
    }

    async function handleUpload(args) {
      const user = harnessUser(args)
      await userInit(user)
      const name0 = sanitize(args && args.name)
      const cat = String((args && args.category) || '').trim() || catOf(name0)
      const name = applyCat(name0, cat)
      const b64 = String((args && args.dataB64) || '')
      if (!b64) return { ok: false, error: '未收到文件数据' }
      if (b64.length > UPLOAD_MAX_B64) return { ok: false, error: '文件过大（超过约 90MB）' }
      const id = newId('u')
      const path = uploadsOf(user) + '/' + id + '__' + name
      // 绕开 stdin 传递的不确定性：base64 先落盘为 .b64 文件，再由 Python 解码
      const b64Path = docRoot(user) + '/tmp/' + id + '.b64'
      try {
        await fs.writeText(await fs.resolve(b64Path), b64, undefined, undefined, policyOf(user))
      } catch (e) {
        return { ok: false, error: '写入临时文件失败: ' + String((e && e.message) || e) }
      }
      const res = await runPy('decode-file ' + q(b64Path) + ' ' + q(path), null, user)
      if (res.exitCode !== 0) {
        return { ok: false, error: '保存失败: ' + errOf(res) }
      }
      const info = { id: id, name: name, kind: 'uploads', user: user, path: path, size: 0, format: fmtOf(name), createdAt: Date.now(), fileMtime: Date.now() }
      try {
        const st = await fs.stat(await fs.resolve(path))
        info.size = (st && st.size) || 0
      } catch (e) {}
      files.set(id, info)
      metaOfUser(user)[id] = { direction: 'upload', mtime: fmtTime(Date.now()), category: catOf(name), request: (args && args.request) || '', summary: (args && args.summary) || '上传文件' }
      saveMeta(user)
      let text = ''
      let chars = 0
      let detail = null
      if (info.format !== 'file' && info.format !== 'ppt') {
        const ex = await runPy('extract ' + q(path), null, user)
        const j = parseResult(ex)
        if (j && j.ok) {
          text = j.text || ''
          chars = j.chars || 0
          detail = { pages: j.pages || 0, slides: j.slides || 0, paragraphs: j.paragraphs || 0, tables: j.tables || 0 }
        }
      }
      return { ok: true, file: pick(info, user), textPreview: text.slice(0, 2000), chars: chars, detail: detail }
    }

    async function handleList(args) {
      const user = harnessUser(args)
      await userInit(user)
      const kind = (args && args.kind) || 'all'
      if (kind === 'uploads' || kind === 'all') await scanDir(uploadsOf(user), 'uploads', user)
      if (kind === 'outputs' || kind === 'all') await scanDir(outputsOf(user), 'outputs', user)
      const catF = String((args && args.category) || '').trim()
      const fmtF = String((args && args.format) || '').toLowerCase()
      const all = []
      files.forEach((f) => { if (f.user === user) all.push(f) })
      all.sort((a, b) => b.createdAt - a.createdAt)
      const picked = all.map((f) => pick(f, user))
      let items = picked
      if (kind !== 'all') items = items.filter((f) => f.kind === kind)
      if (catF) items = items.filter((f) => normCat(f.category) === catF)
      if (fmtF) items = items.filter((f) => f.format === fmtF)
      const categories = []
      const formats = []
      picked.forEach((f) => {
        const c = normCat(f.category)
        if (categories.indexOf(c) < 0) categories.push(c)
        if (formats.indexOf(f.format) < 0) formats.push(f.format)
      })
      return { ok: true, items: items, categories: categories, formats: formats, user: user }
    }

    async function handleParse(args) {
      const user = harnessUser(args)
      const info = fileOf(args && args.fileId, user)
      if (!info) return { ok: false, error: '文件不存在' }
      if (info.format === 'ppt') return { ok: false, error: '旧版 .ppt 无法解析，请另存为 .pptx 后重新上传' }
      const ex = await runPy('extract ' + q(info.path), null, user)
      const j = parseResult(ex)
      if (!j || !j.ok) return { ok: false, error: '解析失败: ' + errOf(ex) }
      const maxChars = (args && args.maxChars) || 50000
      return {
        ok: true,
        fileId: info.id,
        name: info.name,
        text: (j.text || '').slice(0, maxChars),
        chars: j.chars || 0,
        detail: { pages: j.pages || 0, slides: j.slides || 0, paragraphs: j.paragraphs || 0, tables: j.tables || 0 },
      }
    }

    async function handleRemove(args) {
      const user = harnessUser(args)
      const info = fileOf(args && args.fileId, user)
      if (!info) return { ok: false, error: '文件不存在' }
      files.delete(info.id)
      const um = metaOfUser(user)
      if (um[info.id]) {
        delete um[info.id]
        saveMeta(user)
      }
      try {
        const spec = shell.resolve({ command: 'rm -f ' + q(info.path), workdir: userRoot(user), timeoutMs: 30000, sandboxPolicy: policyOf(user) })
        await shell.run(spec)
      } catch (e) {}
      return { ok: true }
    }

    async function handleUrl(args) {
      const user = harnessUser(args)
      const info = fileOf(args && args.fileId, user)
      if (!info) return { ok: false, error: '文件不存在' }
      return { ok: true, url: urlOf(info.id), name: info.name }
    }

    ctx.effect(() => harness.handle('status', (a) => handleStatus(a)))
    ctx.effect(() => harness.handle('upload', (a) => handleUpload(a)))
    ctx.effect(() => harness.handle('list', (a) => handleList(a)))
    ctx.effect(() => harness.handle('parse', (a) => handleParse(a)))
    ctx.effect(() => harness.handle('remove', (a) => handleRemove(a)))
    ctx.effect(() => harness.handle('download-url', (a) => handleUrl(a)))

    async function doCreate(args, user) {
      await userInit(user)
      const fmt = String(args.format || 'docx').toLowerCase()
      if (fmt === 'ppt') return { ok: false, error: '不支持旧版 .ppt 输出，请使用 pptx' }
      const cat = String((args && args.category) || '').trim()
      const baseName = applyCat(args.outputName || ((args.title || '文档') + '.' + fmt), cat)
      const finalName = /\.(docx|pptx|pdf|md|txt|xlsx)$/.test(baseName) ? baseName : baseName + '.' + fmt
      const id = newId('o')
      const path = outputsOf(user) + '/' + id + '__' + finalName
      const res = await runPySpec('create', fmt, path, null, {
        title: args.title || '',
        subtitle: args.subtitle || '',
        author: args.author || '',
        date: args.date || '',
        theme: args.theme || 'blue',
        style: args.style,
        content: args.content || '',
        sections: args.sections,
      }, user)
      if (res.exitCode !== 0) {
        return { ok: false, error: '生成失败: ' + errOf(res, 500) }
      }
      const info = { id: id, name: finalName, kind: 'outputs', user: user, path: path, size: 0, format: fmt, createdAt: Date.now(), fileMtime: Date.now() }
      try {
        const st = await fs.stat(await fs.resolve(path))
        info.size = (st && st.size) || 0
      } catch (e) {}
      files.set(id, info)
      metaOfUser(user)[id] = {
        direction: 'output',
        mtime: fmtTime(Date.now()),
        category: catOf(finalName),
        request: (args && args.request) || '',
        summary: (args && args.summary) || '生成 ' + fmt.toUpperCase() + ' 文档',
      }
      saveMeta(user)
      return {
        ok: true,
        value: { fileId: id, fileName: finalName, format: fmt, size: info.size, downloadUrl: urlOf(id), message: '生成成功' },
      }
    }

    async function doEdit(args, user) {
      const info = fileOf(args && args.sourceFileId, user)
      if (!info) return { ok: false, error: '找不到源文件 ' + String(args && args.sourceFileId) + '，请先用 docflow_list_documents 查看可用文件' }
      let fmt = String(args.format || info.format).toLowerCase()
      if (fmt === 'markdown') fmt = 'md'
      if (fmt === 'ppt') return { ok: false, error: '旧版 .ppt 无法编辑，请另存为 .pptx 后重新上传' }
      if (['docx', 'pptx', 'pdf', 'md', 'txt', 'xlsx'].indexOf(fmt) < 0) return { ok: false, error: '不支持的格式: ' + fmt }
      const um = metaOfUser(user)
      const srcCat = (um[info.id] && um[info.id].category) || ''
      const cat = (args && args.category) ? String(args.category).trim() : srcCat
      const base = stripCat(String(info.name)).replace(/\.[^.]+$/, '') || '文档'
      const outName = applyCat(args.outputName || (base + '_修改.' + fmt), cat)
      const finalName = /\.(docx|pptx|pdf|md|txt)$/.test(outName) ? outName : outName + '.' + fmt
      const id = newId('o')
      const path = outputsOf(user) + '/' + id + '__' + finalName
      const spec = { theme: 'blue', ops: args.ops || [] }
      // 引擎 edit 参数顺序：edit <fmt> <源文件> <输出> [spec]
      const specPath = await writeJsonTemp(spec, user)
      const res = await runPy('edit ' + fmt + ' ' + q(info.path) + ' ' + q(path) + ' ' + q(specPath), null, user)
      if (res.exitCode !== 0) {
        return { ok: false, error: '修改失败: ' + errOf(res, 500) }
      }
      const nfo = { id: id, name: finalName, kind: 'outputs', user: user, path: path, size: 0, format: fmt, createdAt: Date.now(), fileMtime: Date.now() }
      try {
        const st = await fs.stat(await fs.resolve(path))
        nfo.size = (st && st.size) || 0
      } catch (e) {}
      files.set(id, nfo)
      um[id] = {
        direction: 'output',
        mtime: fmtTime(Date.now()),
        category: catOf(finalName),
        request: (args && args.request) || '',
        summary: (args && args.summary) || opsSummary(args.ops),
      }
      saveMeta(user)
      return {
        ok: true,
        value: { fileId: id, fileName: finalName, format: fmt, size: nfo.size, downloadUrl: urlOf(id), message: '修改成功' },
      }
    }

    const OUT_SCHEMA = {
      type: 'object',
      additionalProperties: true,
      properties: {
        fileId: { type: 'string' },
        fileName: { type: 'string' },
        format: { type: 'string' },
        size: { type: 'integer' },
        downloadUrl: { type: 'string' },
        message: { type: 'string' },
      },
    }

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_create_document',
      description: '根据 markdown 内容生成精美文档（docx/pptx/pdf/md/xlsx）。docx/pptx/pdf 含封面、主题配色、标题、列表、表格、引用、代码块、页眉页脚页码；xlsx 按表格数据生成带主题配色的 Excel。pptx 可指定 style=visual 启用可视化大字版（正文最小24pt、卡片网格、大色块）。生成后文件出现在浏览器的「文档工作流」面板并可下载。',
      parameters: {
        format: { type: 'string', enum: ['docx', 'pptx', 'pdf', 'md', 'xlsx'], required: true, description: '输出格式：docx=Word、pptx=PPT、pdf=PDF、md=Markdown、xlsx=Excel' },
        title: { type: 'string', required: true, description: '文档标题（封面主标题）' },
        subtitle: { type: 'string', description: '封面副标题' },
        author: { type: 'string', description: '作者/单位' },
        date: { type: 'string', description: '日期文字，如 2026年8月' },
        theme: { type: 'string', enum: ['blue', 'green', 'red', 'purple', 'gold', 'slate'], description: '配色主题，默认 blue' },
        style: { type: 'string', enum: ['classic', 'visual'], description: 'pptx 排版风格：classic=麦肯锡经典（默认）；visual=可视化大字版（正文最小24pt，卡片网格铺满页面，适合演示/教程）' },
        request: { type: 'string', description: '用户要求（一句话记录在文件列表中，便于追溯本次生成目的）' },
        content: { type: 'string', description: '正文 markdown：\\n# 一级标题 / ## 二级标题 / ### 三级标题 / 普通段落 / - 无序列表 / 1. 有序列表 / > 引用 / | 表头 | 表头 | + | --- | --- | + 数据行 / ```代码块``` / --- 分隔线' },
        outputName: { type: 'string', description: '输出文件名（可省略扩展名）' },
        category: { type: 'string', description: '文件分类（如 命理分析、科研申报书、测试），将以【分类】前缀加入文件名，便于按分类筛选' },
      },
      output: {
        schema: OUT_SCHEMA,
        render(args, value) {
          return [{ type: 'text', text: '已生成 ' + String(value.format || '').toUpperCase() + ' 文档「' + value.fileName + '」（' + kb(value.size) + '）。\\n下载：' + value.downloadUrl }]
        },
      },
      async execute(args, exec) {
        const r = await doCreate(args, userOfExec(exec))
        if (!r.ok) throw new Error(r.error)
        return r.value
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_edit_document',
      description: '修改已有的上传或生成文档：查找替换文本、改标题、追加内容（markdown）、更换主题色。输出为新文件，可下载。',
      parameters: {
        sourceFileId: { type: 'string', required: true, description: '源文件 ID（docflow_list_documents 查看）' },
        format: { type: 'string', enum: ['docx', 'pptx', 'pdf', 'md', 'txt', 'xlsx'], description: '源文件格式，缺省自动判断' },
        ops: {
          type: 'array',
          required: true,
          description: '编辑操作列表，按顺序执行',
          items: {
            type: 'object',
            additionalProperties: true,
            properties: {
              type: { type: 'string', enum: ['replace', 'set-title', 'append', 'restyle'], required: true, description: 'replace=查找替换；set-title=改标题；append=追加内容；restyle=换主题色' },
              find: { type: 'string', description: 'replace 操作的查找文本' },
              replace: { type: 'string', description: 'replace 操作的替换文本' },
              title: { type: 'string', description: 'set-title 操作的新标题' },
              content: { type: 'string', description: 'append 操作追加的 markdown 内容' },
              accent: { type: 'string', description: 'restyle 操作的新主题色，如 #1F6FB2' },
            },
          },
        },
        outputName: { type: 'string', description: '输出文件名（可省略扩展名）' },
        category: { type: 'string', description: '文件分类（如 命理分析、科研申报书、测试），将以【分类】前缀加入输出文件名；缺省继承源文件分类' },
        request: { type: 'string', description: '用户要求（一句话记录在文件列表中，便于追溯本次修改目的）' },
      },
      output: {
        schema: OUT_SCHEMA,
        render(args, value) {
          return [{ type: 'text', text: '已修改并生成新文档「' + value.fileName + '」（' + kb(value.size) + '）。\\n下载：' + value.downloadUrl }]
        },
      },
      async execute(args, exec) {
        const r = await doEdit(args, userOfExec(exec))
        if (!r.ok) throw new Error(r.error)
        return r.value
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_list_documents',
      description: '列出文档工作流中已上传和已生成的所有文件（含下载地址），可按分类和格式筛选。',
      parameters: {
        kind: { type: 'string', enum: ['uploads', 'outputs', 'all'], description: '列出范围，默认 all' },
        category: { type: 'string', description: '按分类筛选（如 命理分析、科研申报书、测试；无分类文件用 未分类）' },
        format: { type: 'string', description: '按格式筛选（docx/pptx/pdf/md/txt/xlsx 等）' },
      },
      output: {
        schema: { type: 'object', additionalProperties: true, properties: { items: { type: 'array', items: { type: 'json' } }, categories: { type: 'array', items: { type: 'string' } }, formats: { type: 'array', items: { type: 'string' } } } },
        render(args, value) {
          const items = value.items || []
          const lines = items.map((i) => (i.kind === 'outputs' ? '[生成] ' : '[上传] ') + i.name + ' (' + i.format + ', ' + kb(i.size) + ')\\n  下载: ' + i.downloadUrl)
          return [{ type: 'text', text: '共 ' + items.length + ' 个文件：\\n' + (lines.join('\\n') || '（空）') }]
        },
      },
      async execute(args, exec) {
        const r = await handleList(Object.assign({}, args || {}, { user: userOfExec(exec) }))
        if (!r.ok) throw new Error(r.error)
        return { items: r.items, categories: r.categories, formats: r.formats }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_parse_document',
      description: '提取上传/生成文档的纯文本内容（docx/pdf/pptx/txt/md），用于理解源文档后创建或修改。',
      parameters: {
        fileId: { type: 'string', required: true, description: '文件 ID' },
        maxChars: { type: 'integer', description: '最多返回字符数，默认 50000' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            fileId: { type: 'string' },
            name: { type: 'string' },
            text: { type: 'string' },
            chars: { type: 'integer' },
            detail: { type: 'json' },
          },
        },
        render(args, value) {
          return [{ type: 'text', text: '「' + value.name + '」共 ' + value.chars + ' 字' + (value.detail ? '（' + JSON.stringify(value.detail) + '）' : '') + '，内容见调用结果。' }]
        },
      },
      async execute(args, exec) {
        const r = await handleParse(Object.assign({}, args || {}, { user: userOfExec(exec) }))
        if (!r.ok) throw new Error(r.error)
        return { fileId: r.fileId, name: r.name, text: r.text, chars: r.chars, detail: r.detail }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_export_document',
      description: '格式转换：把已有文档内容提取后重新排版为另一种格式（docx/pptx/pdf）。',
      parameters: {
        fileId: { type: 'string', required: true, description: '源文件 ID' },
        format: { type: 'string', enum: ['docx', 'pptx', 'pdf'], required: true, description: '目标格式' },
        outputName: { type: 'string', description: '输出文件名（可省略扩展名）' },
        category: { type: 'string', description: '文件分类（如 命理分析、科研申报书、测试），将以【分类】前缀加入输出文件名；缺省继承源文件分类' },
      },
      output: {
        schema: OUT_SCHEMA,
        render(args, value) {
          return [{ type: 'text', text: '已转换为 ' + String(value.format || '').toUpperCase() + '：「' + value.fileName + '」（' + kb(value.size) + '）。\\n下载：' + value.downloadUrl }]
        },
      },
      async execute(args, exec) {
        const user = userOfExec(exec)
        const info = fileOf(args && args.fileId, user)
        if (!info) throw new Error('找不到文件 ' + String(args && args.fileId) + '，请先用 docflow_list_documents 查看')
        const fmt = String(args.format || '').toLowerCase()
        if (['docx', 'pptx', 'pdf'].indexOf(fmt) < 0) throw new Error('目标格式仅支持 docx/pptx/pdf')
        if (info.format === 'ppt') throw new Error('旧版 .ppt 无法读取，请另存为 .pptx 后重新上传')
        const ex = await runPy('extract ' + q(info.path), null, user)
        const j = parseResult(ex)
        if (!j || !j.ok) throw new Error('无法读取源文件内容: ' + errOf(ex, 300))
        const base = stripCat(String(info.name)).replace(/\.[^.]+$/, '') || '文档'
        const srcCat = (metaOfUser(user)[info.id] && metaOfUser(user)[info.id].category) || ''
        const createArgs = {
          format: fmt,
          title: base,
          content: (j.text || '').slice(0, 200000),
          outputName: args.outputName,
          category: srcCat,
        }
        const r = await doCreate(createArgs, user)
        if (!r.ok) throw new Error(r.error)
        return r.value
      },
    })))

    // ---------- 文献工具 ----------
    const LIT_SCHEMA = {
      type: 'object',
      additionalProperties: true,
      properties: {
        ok: { type: 'boolean' },
        count: { type: 'integer' },
        items: { type: 'array', items: { type: 'json' } },
        results: { type: 'array', items: { type: 'json' } },
        error: { type: 'string' },
      },
    }

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_literature_search',
      description: '从真实来源（PubMed/Medline，经 NCBI E-utilities 官方 API）检索医学文献，返回带 PMID、作者、期刊、年卷期页、DOI、摘要及 GB/T 7714-2015 顺序编码制引文格式的结构化条目，用于撰写/审阅论文参考文献。',
      parameters: {
        term: { type: 'string', required: true, description: 'PubMed 检索式，如 oral lichen planus corticosteroid randomized（支持 AND/OR/引号精确短语）' },
        maxResults: { type: 'integer', description: '最多返回条数，默认 8，上限 20' },
      },
      output: {
        schema: LIT_SCHEMA,
        render(args, value) {
          const items = value.items || []
          const lines = items.map((it, i) => '[' + (i + 1) + '] ' + it.citation + (it.abstract ? '\n    摘要: ' + it.abstract.slice(0, 200) : ''))
          return [{ type: 'text', text: 'PubMed 命中 ' + (value.count != null ? value.count : items.length) + ' 条，返回 ' + items.length + ' 条：\n' + (lines.join('\n') || '（无结果）') }]
        },
      },
      async execute(args) {
        const r = await handleLitSearch(args)
        if (!r.ok) throw new Error(r.error)
        return { ok: true, count: r.count, items: r.items }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_literature_crossref',
      description: '通过 Crossref 官方 API（DOI 权威注册库）检索文献，用于补充 PubMed 未收录的文献（含中文期刊、会议论文、专著章节），返回带 DOI 与 GB/T 7714 引文格式的条目。',
      parameters: {
        query: { type: 'string', required: true, description: '检索词（标题/作者/期刊）' },
        maxResults: { type: 'integer', description: '最多返回条数，默认 5，上限 10' },
      },
      output: {
        schema: LIT_SCHEMA,
        render(args, value) {
          const items = value.items || []
          const lines = items.map((it, i) => '[' + (i + 1) + '] ' + it.citation)
          return [{ type: 'text', text: 'Crossref 返回 ' + items.length + ' 条：\n' + (lines.join('\n') || '（无结果）') }]
        },
      },
      async execute(args) {
        const r = await handleLitCrossref(args)
        if (!r.ok) throw new Error(r.error)
        return { ok: true, items: r.items }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_literature_verify',
      description: '核查用户提供的引文真实性：逐条与 PubMed（标题/PMID）和 Crossref（DOI/标题）官方数据比对，返回 verified 真伪结论、匹配到的真实元数据与正确的 GB/T 7714-2015 引文格式，防止引用不存在的文献。',
      parameters: {
        references: {
          type: 'array',
          required: true,
          description: '待核查引文列表，每项可含 title/authors/year/doi/pmid 任一字段',
          items: {
            type: 'object',
            additionalProperties: true,
            properties: {
              title: { type: 'string', description: '文献标题' },
              authors: { type: 'array', items: { type: 'string' }, description: '作者列表' },
              year: { type: 'string', description: '发表年份' },
              doi: { type: 'string', description: 'DOI' },
              pmid: { type: 'string', description: 'PubMed ID' },
            },
          },
        },
      },
      output: {
        schema: LIT_SCHEMA,
        render(args, value) {
          const results = value.results || []
          const lines = results.map((r, i) => {
            const head = r.input && (r.input.title || r.input.doi || r.input.pmid) ? (r.input.title || r.input.doi || r.input.pmid) : ('引文' + (i + 1))
            return '[' + (i + 1) + '] ' + head + ' → ' + (r.verified ? '✅ 真实' : '❌ 未核实') + '（' + (r.notes || []).join('；') + '）' + (r.matched && r.matched.citation ? '\n    正确格式: ' + r.matched.citation : '')
          })
          return [{ type: 'text', text: '核查 ' + results.length + ' 条：\n' + (lines.join('\n') || '（无结果）') }]
        },
      },
      async execute(args) {
        const r = await handleLitVerify(args)
        if (!r.ok) throw new Error(r.error)
        return { ok: true, results: r.results }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_image_search',
      description: '从网络搜索图片或矢量图（当前使用 Wikimedia Commons，无需 API Key），返回可下载 URL、缩略图、尺寸与类型，便于插入 PPT/文档。',
      parameters: {
        query: { type: 'string', required: true, description: '搜索词，如 口腔黏膜 病理 示意图' },
        maxResults: { type: 'integer', description: '最多返回条数，默认 5，上限 20' },
        type: { type: 'string', enum: ['photo', 'vector', 'all'], description: 'photo=位图照片/插画；vector=SVG矢量图；all=全部' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            items: { type: 'array', items: { type: 'json' } },
          },
        },
        render(args, value) {
          const items = value.items || []
          const lines = items.map((it, i) => '[' + (i + 1) + '] ' + (it.title || '') + '\n    类型: ' + (it.mime || '') + '  ' + (it.width || 0) + 'x' + (it.height || 0) + '\n    下载: ' + (it.thumb || it.url || ''))
          return [{ type: 'text', text: '图片搜索返回 ' + items.length + ' 条：\n' + (lines.join('\n') || '（无结果）') }]
        },
      },
      async execute(args) {
        const r = await handleImageSearch(args)
        if (!r.ok) throw new Error(r.error)
        return { ok: true, items: r.items }
      },
    })))

    ctx.effect(() => harness.registerTool(ctx, harness.defineTool({
      name: 'docflow_image_recognize',
      description: '识别图片：返回图片格式/尺寸/主色，并尝试 OCR 文字识别；如配置视觉 API 则返回图片内容描述。',
      parameters: {
        fileId: { type: 'string', description: '已上传图片的文件 ID（docflow_list_documents 查看）' },
        path: { type: 'string', description: '或直接传服务器本地图片路径' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            info: { type: 'json' },
            ocr: { type: 'string' },
            description: { type: 'string' },
            vision_error: { type: 'string' },
          },
        },
        render(args, value) {
          const info = value.info || {}
          const lines = [
            '格式: ' + (info.format || ''),
            '尺寸: ' + (info.width || '') + 'x' + (info.height || ''),
            '主色: ' + (info.dominant_rgb || ''),
          ]
          if (value.ocr) lines.push('OCR: ' + value.ocr)
          if (value.description) lines.push('描述: ' + value.description)
          if (value.vision_error) lines.push('视觉API提示: ' + value.vision_error)
          return [{ type: 'text', text: lines.join('\n') }]
        },
      },
      async execute(args, exec) {
        const r = await handleImageRecognize(Object.assign({}, args || {}, { user: userOfExec(exec) }))
        if (!r.ok) throw new Error(r.error)
        return r
      },
    })))

    console.log('docflow 就绪: ' + ROOT)
  },
}
